"""Reconstruct GitHub receipts only when WeChat draft/add was confirmed.

No network, no WeChat API. Incomplete/ambiguous journals are NEVER recovered
automatically. The stored PASS-gate snapshot must bind the exact archive hash.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

PROFILES = ("qiezhi", "wechat", "business", "zizhitongjian",
            "parenting", "jingyun", "fashion")


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def reconcile(root: Path, profile: str, day: str) -> dict:
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
    base = root / profile
    archive = base / "archive" / (day + ".md")
    journal_path = base / "status" / "draft-attempts" / (day + ".json")
    journal = _read(journal_path)
    if journal.get("state") != "confirmed":
        return {"profile": profile, "result": "skip_no_confirmed_journal"}
    if not archive.is_file():
        return {"profile": profile, "result": "skip_archive_missing"}
    raw = archive.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    title = next((line[2:].strip() for line in raw.decode("utf-8").splitlines()
                  if line.startswith("# ")), "")
    expected_path = profile + "/archive/" + day + ".md"
    if (journal.get("article_path") != expected_path or
            journal.get("article_sha256") != digest or
            journal.get("profile") != profile or
            journal.get("title") != title or
            not journal.get("draft_media_id") or not title):
        return {"profile": profile, "result": "blocked_journal_archive_conflict"}
    snapshot = journal.get("passed_gates")
    gate_names = ["quality-gate.json", "visual-gate.json"]
    if profile == "fashion":
        gate_names.append("image-gate.json")
    if profile == "zizhitongjian":
        gate_names.append("source-gate.json")
    if not isinstance(snapshot, dict) or set(snapshot) != set(gate_names):
        return {"profile": profile, "result": "blocked_missing_gate_snapshot"}
    for name in gate_names:
        gate = snapshot.get(name)
        if (not isinstance(gate, dict) or gate.get("status") != "PASS" or
                gate.get("article_sha256") != digest or
                gate.get("article_path") != expected_path):
            return {"profile": profile, "result": "blocked_untrusted_gate_snapshot"}
    status_path = base / "status" / "latest.json"
    old = _read(status_path)
    if old.get("status") == "success" and old.get("article_path") == expected_path:
        if old.get("article_sha256") != digest or old.get("title") != title:
            return {"profile": profile, "result": "blocked_existing_receipt_conflict"}
        return {"profile": profile, "result": "already_confirmed"}
    # An older successful day's status is allowed to be superseded by a
    # verified NEW confirmed journal, but is never overwritten without proof.
    today = base / "articles" / "today.md"
    today.parent.mkdir(parents=True, exist_ok=True)
    today.write_bytes(raw)
    for name in gate_names:
        path = base / "status" / name
        record = dict(snapshot[name])
        if name == "visual-gate.json":
            # Preserve independently verified draft/get proof if restoring a
            # confirmed journal would otherwise overwrite the Visual Gate.
            proof = _read(base / "status" / "draft-readback" / (day + ".json"))
            if (proof.get("draft_get_verified") is True and
                proof.get("draft_media_id") == journal["draft_media_id"] and
                proof.get("article_sha256") == digest and
                proof.get("article_path") == expected_path and
                proof.get("article_date") == day and
                (proof.get("inline_image_count") or 0) >=
                    (5 if profile == "fashion" else 1)):
                record["wechat_inline_readback"] = proof
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", "utf-8")
    status = {
        "status": "success",
        "title": title,
        "article_path": expected_path,
        "article_sha256": digest,
        "draft_media_id": journal["draft_media_id"],
        "workflow_run_id": str(journal.get("run_id", "")),
        "recovered_from_confirmed_journal": True,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return {"profile": profile, "result": "recovered_confirmed_without_wechat_call"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    day = args.date or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    results = [reconcile(args.root, p, day) for p in PROFILES]
    print(json.dumps({"date": day, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
