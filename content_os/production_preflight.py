"""Read-only production handoff classifier. Never calls any WeChat API.

A stale or missing research report is an editorial caveat, not permission to
skip all writing or to mislabel yesterday's work as today. This script is a
checkpoint for ChatGPT writing tasks and GitHub's non-publishing watchdog.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from content_os.daily_healthcheck import PROFILES, audit_profile, read_json
except ImportError:
    from daily_healthcheck import PROFILES, audit_profile, read_json

TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]


def _freshness(root: Path, day: str) -> dict:
    sources = {
        "source_health": ("source-health/latest.json", "date"),
        "editorial_intelligence": (f"editorial-intelligence/{day}.json", "date"),
        "reading_feedback": ("reading-feedback/latest.json", "generated_at"),
        "daily_health": ("daily-health/latest.json", "date"),
        "topic_intelligence": ("topic-intelligence/latest.json", "local_date"),
    }
    out = {}
    for name, (filename, key) in sources.items():
        data = read_json(root / "content_os" / filename)
        recorded = str(data.get(key) or "")[:10] or None
        out[name] = {"recorded_date": recorded, "fresh": recorded == day}
    return out


def inspect(root: Path, day: str | None = None) -> dict:
    day = day or datetime.now(TZ).date().isoformat()
    # Reject malformed date rather than reading arbitrary file names.
    if datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
        raise ValueError("expected an ISO calendar date")
    results = {}
    for profile in PROFILES:
        base = root / profile
        archive = base / "archive" / (day + ".md")
        journal_path = base / "status" / "draft-attempts" / (day + ".json")
        status = read_json(base / "status" / "latest.json")
        journal = read_json(journal_path)
        archive_exists = archive.is_file()
        status_path = status.get("article_path") or ""
        today_receipt = (
            status_path == f"{profile}/archive/{day}.md"
            or (status.get("status") == "success" and day in status_path)
        )
        reasons = []
        if journal_path.exists():
            # Any journal, including malformed/attempted/confirmed-but-mismatched,
            # is an immutable remote API attempt until conclusively reconciled.
            audited = audit_profile(root, profile, day) if archive_exists else {}
            if journal.get("state") == "confirmed" and audited.get("status") == "success":
                action = "skip_confirmed"
            else:
                action = "manual_review_required"
                reasons.append("draft_journal_present_not_fully_reconciled")
                reasons.extend(audited.get("errors", []))
        elif today_receipt:
            action = "manual_review_required"
            reasons.append("today_receipt_without_durable_journal")
        elif archive_exists:
            # Reading local state cannot prove that the draft API was not reached.
            # A human/agent must inspect Actions run, job, logs before dispatch.
            action = "inspect_actions_before_dispatch"
            reasons.append("archive_exists_no_attempt_journal_check_remote_runs")
        else:
            action = "write_new_archive"
            reasons.append("today_archive_missing")
        results[profile] = {
            "action": action,
            "archive": f"{profile}/archive/{day}.md",
            "archive_exists": archive_exists,
            "journal_state": journal.get("state") if journal_path.exists() else None,
            "receipt_path": status_path or None,
            "reasons": list(dict.fromkeys(reasons)),
        }
    return {
        "date": day, "timezone": "Asia/Shanghai",
        "generated_at": datetime.now(TZ).isoformat(),
        "editorial_brief": "content_os/PRODUCTION_BRIEF.md",
        "delivery_goal": (
            "每号交付完整好稿与实际看过、贴合正文的图片，并确认送达微信公众号草稿箱。"
            "逐号完成研究、写作、配图、删改、送稿与回读。"
            "记录和测试不能代替成品；必须先阅读PRODUCTION_BRIEF.md的成品验收要求。"
        ),
        "editorial_feedback": "content_os/editorial-feedback.json",
        "editorial_review_required_from": "2026-10-14",
        "profiles": results,
        "input_freshness": _freshness(root, day),
        "confirmed_count": sum(v["action"] == "skip_confirmed" for v in results.values()),
        "missing_archives": [p for p,v in results.items() if v["action"] == "write_new_archive"],
        "manual_review": [p for p,v in results.items() if v["action"] == "manual_review_required"],
        "policy": (
            "Missing/stale research, reading feedback and health are NON-BLOCKING "
            "for responsible original writing. Record insufficient_evidence, "
            "verify facts independently, and complete permitted accounts one by one. "
            "This classifier NEVER authorizes draft/add; inspect Actions and run "
            "all applicable gates before archive creation or API access."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--date", default=datetime.now(TZ).date().isoformat())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = inspect(args.root, args.date)
    raw = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8")
    print(raw, end="")
    return int(args.strict and report["confirmed_count"] != len(PROFILES))


if __name__ == "__main__":
    raise SystemExit(main())
