"""Daily seven-profile draft audit; no login, API key or publishing.

A SUCCESS means repo artifact/status consistency, not a human visual
inspection of the WeChat backend. Never create or send a draft here.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

PROFILES = ("qiezhi", "wechat", "business", "zizhitongjian",
            "parenting", "jingyun", "fashion")
LOCAL = ZoneInfo("Asia/Shanghai")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def title_for(text: str) -> str:
    return next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")


def audit_profile(root: Path, profile: str, day: str) -> dict:
    base = root / profile
    archive = base / "archive" / (day + ".md")
    today = base / "articles" / "today.md"
    status = read_json(base / "status" / "latest.json")
    errors = []
    digest = None
    title = ""
    raw = None
    try:
        raw = archive.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        title = title_for(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        errors.append("archive_missing_or_unreadable")
    if not title:
        errors.append("archive_title_missing")
    if status.get("status") != "success":
        errors.append("no_success_receipt")
    if digest and status.get("article_sha256") != digest:
        errors.append("receipt_sha_mismatch_or_stale")
    if title and status.get("title") != title:
        errors.append("receipt_title_mismatch")
    reported_path = status.get("article_path")
    expected_path = (base / "archive" / (day + ".md")).relative_to(root).as_posix()
    if reported_path != expected_path:
        errors.append("receipt_date_mismatch")
    if raw is not None:
        try:
            if today.read_bytes() != raw:
                errors.append("today_not_identical_to_archive")
        except OSError:
            errors.append("today_missing")
    gates = ["quality-gate.json", "visual-gate.json"]
    if profile == "fashion":
        gates.insert(0, "image-gate.json")
    if profile == "zizhitongjian":
        gates.insert(0, "source-gate.json")
    gate_data = {}
    for gate in gates:
        check = read_json(base / "status" / gate)
        gate_data[gate] = check.get("status") or "MISSING"
        if check.get("status") != "PASS":
            errors.append("gate_missing_or_not_pass:" + gate)
        # Gate reports generated before the 2026-10-11 rollout lack a bound hash.
        # All subsequent PASS values must prove they checked these exact bytes.
        if day >= "2026-10-11" and (
            check.get("article_sha256") != digest or
            check.get("article_path") != expected_path
        ):
            errors.append("gate_not_bound_to_archive:" + gate)
    # Starting the first full post-rollout day, success MUST have a durable
    # confirmation of the exact WeChat draft/add request and its media_id.
    journal = read_json(base / "status" / "draft-attempts" / (day + ".json"))
    if day >= "2026-10-11":
        if (journal.get("state") != "confirmed" or
            journal.get("article_sha256") != digest or
            journal.get("article_path") != expected_path or
            not journal.get("draft_media_id")):
            errors.append("draft_add_journal_missing_or_unconfirmed")
    fashion_revision = None
    if profile == "fashion":
        revised = base / "revisions" / (day + ".md")
        if revised.is_file():
            revision_raw = revised.read_bytes()
            revision_sha = hashlib.sha256(revision_raw).hexdigest()
            revision_title = title_for(revision_raw.decode("utf-8"))
            revision_status = read_json(base / "status" / "revisions" / (day + ".json"))
            fashion_revision = {
                "article_path": revised.relative_to(root).as_posix(),
                "title": revision_title,
                "status": revision_status.get("status") or "pending",
                "workflow_run_id": revision_status.get("workflow_run_id"),
            }
            if (revision_status.get("status") != "success" or
                revision_status.get("revision_sha256") != revision_sha or
                revision_status.get("revision_path") != revised.relative_to(root).as_posix() or
                revision_status.get("revision_title") != revision_title or
                revision_status.get("original_article_path") != expected_path or
                revision_status.get("operation") != "in_place_draft_update" or
                not revision_status.get("draft_media_id")):
                errors.append("fashion_explicit_revision_pending_or_unverified")
    source = read_json(base / "status" / "source-gate.json") if profile == "zizhitongjian" else {}
    return {
        "profile": profile, "status": "success" if not errors else "incomplete",
        "archive": archive.relative_to(root).as_posix(),
        "title": title, "workflow_run_id": status.get("workflow_run_id"),
        "gates": gate_data,
        "journal_state": journal.get("state") or "MISSING",
        "fashion_revision": fashion_revision,
        "draft_media_id_recorded": bool(journal.get("draft_media_id")),
        "verification_mode": source.get("verification_mode") if source else None,
        "image_check_done": source.get("image_check_done") if source else None,
        "errors": errors,
    }


def make_report(root: Path, day: str | None = None) -> dict:
    day = day or datetime.now(LOCAL).date().isoformat()
    accounts = {p: audit_profile(root, p, day) for p in PROFILES}
    successes = sum(v["status"] == "success" for v in accounts.values())
    intel = read_json(root / "content_os" / "topic-intelligence" / (day + ".json"))
    return {
        "date": day,
        "generated_at": datetime.now(LOCAL).isoformat(),
        "timezone": "Asia/Shanghai",
        "status": "complete" if successes == len(PROFILES) else "incomplete",
        "success_count": successes,
        "expected_count": len(PROFILES),
        "accounts": accounts,
        "topic_scan_date": intel.get("local_date"),
        "topic_scan_available": bool(intel.get("profiles")),
        "topic_popularity_verified_count": {
            p: (intel.get("profiles", {}).get(p, {}) or {}).get("heat_evidence_count", 0)
            for p in PROFILES
        },
        "note": "Repo receipt + hash + today's article + gates; not direct WeChat UI visual confirmation.",
    }


def write_report(report: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    data = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (folder / (report["date"] + ".json")).write_text(data, encoding="utf-8")
    (folder / "latest.json").write_text(data, encoding="utf-8")
    rows = [
        "# 七公众号草稿健康检查 " + report["date"], "",
        f"已完成 {report['success_count']}/{report['expected_count']}；状态：{report['status']}",
        "", "| 方向 | 草稿回执+归档一致 | 失败环节 |", "|---|---|---|",
    ]
    for k, d in report["accounts"].items():
        rows.append(f"| {k} | {d['status']} | {', '.join(d['errors']) or '无'} |")
    rows.extend(["", "注：这是仓库/工作流回执核验，并非微信公众号后台视觉验收。"])
    if not report["topic_scan_available"]:
        rows.append("选题扫描数据缺失；此状态不得阻断合格文章写作。")
    markdown = "\n".join(rows) + "\n"
    (folder / (report["date"] + ".md")).write_text(markdown, encoding="utf-8")
    (folder / "latest.md").write_text(markdown, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--date")
    ap.add_argument("--output-dir", type=Path)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    report = make_report(args.root, args.date)
    if args.output_dir:
        write_report(report, args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if args.strict and report["status"] != "complete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
