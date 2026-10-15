"""Fail-closed, per-article dispatch reservation for extra WeChat drafts.

Called ONLY by the existing approved-candidate promotion workflow. Writes a
durable marker in the checkout BEFORE gh workflow run. The marker is committed
and pushed BEFORE dispatch, and is NEVER silently removed or reused: an
unknown workflow_dispatch outcome must not result in a duplicate draft/add.
Does not call WeChat or GitHub API and does not touch inbox/archive.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from content_os.multi_draft import get_article_identity, verify_article_approval
except ImportError:
    from multi_draft import get_article_identity, verify_article_approval

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")


def reserve(root: Path, profile: str, article_path: str, *, now=None) -> dict:
    root = root.resolve()
    candidate = Path(article_path)
    expected_location = root / candidate
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("article_path_must_be_repo_relative")
    if not expected_location.is_file() or expected_location.is_symlink():
        raise ValueError("approved_archive_missing_or_symlink")
    day, article_id = get_article_identity(candidate, profile)
    if article_id == day or day < "2026-10-15":
        raise ValueError("only_new_supplementary_article_ids_supported")
    local_day = (now or datetime.now(TZ)).astimezone(TZ).date().isoformat()
    if day != local_day:
        raise ValueError("not_today_no_late_dispatch")
    actual = root / profile / "archive" / (article_id + ".md")
    if expected_location.resolve() != actual.resolve():
        raise ValueError("article_archive_path_mismatch")
    raw = actual.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    approval_errors = verify_article_approval(root, profile, article_id, raw.decode("utf-8"))
    if approval_errors:
        raise ValueError("exact_user_approval_missing:" + ",".join(approval_errors))
    journal = root / profile / "status" / "draft-attempts" / (article_id + ".json")
    receipt = root / profile / "status" / "receipts" / (article_id + ".json")
    readback = root / profile / "status" / "draft-readback" / (article_id + ".json")
    if journal.exists() or receipt.exists() or readback.exists():
        raise ValueError("already_attempted_confirmed_or_unknown_no_auto_retry")
    marker = root / "content_os" / "dispatch-reservations" / profile / (article_id + ".json")
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile,
        "article_id": article_id,
        "article_path": candidate.as_posix(),
        "article_sha256": digest,
        "reserved_at": (now or datetime.now(TZ)).astimezone(TZ).isoformat(),
        "state": "reserved_before_workflow_dispatch",
        "note": "Missing journal or uncertain dispatch result is not permission to retry."
    }
    # Never overwrite a previous marker, including a corrupt one.
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError("prior_dispatch_reservation_exists_manual_review_only") from None
    with os.fdopen(descriptor, "wb") as file:
        file.write(encoded)
    return {"status": "RESERVED_NO_DISPATCH_YET", "reservation_path": marker.relative_to(root).as_posix(),
            "article_sha256": digest, "article_id": article_id}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--article", required=True)
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args()
    try:
        result = reserve(args.root, args.profile, args.article)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
