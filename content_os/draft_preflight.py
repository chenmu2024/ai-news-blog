"""Idempotency guard for WeChat draft workflows. Standard library only.

A retry must not post the same immutable archived Markdown twice after a
successful status commit. This checks the exact SHA-256, not just the date.
A failed or stale status never claims a draft exists.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
try:
    from content_os.draft_journal import locate
except ImportError:
    from draft_journal import locate


def inspect(article: Path, profile: str, status_dir: Path | None = None) -> dict:
    if profile not in {"qiezhi", "wechat", "business", "zizhitongjian",
                       "parenting", "jingyun", "fashion"}:
        raise ValueError(f"Unknown profile: {profile}")
    if not article.is_file() or article.parent.name != "archive" or article.parent.parent.name != profile:
        raise ValueError(f"Expected {profile}/archive/YYYY-MM-DD.md: {article}")
    if not (len(article.stem) == 10 and article.stem[4] == "-" and article.stem[7] == "-"):
        raise ValueError("Archive filename must be a calendar date")
    raw = article.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    status_file = status_dir / "latest.json" if status_dir else Path(profile) / "status" / "latest.json"
    try:
        last = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        last = {}
    title = next((line[2:].strip() for line in raw.decode("utf-8").splitlines()
                  if line.startswith("# ")), "")
    confirmed = (
        last.get("status") == "success"
        and last.get("article_sha256") == digest
        and last.get("title") == title
        and (last.get("article_path") in (None, "", article.as_posix()))
    )
    # A remote write-ahead journal is present before draft/add. Even if GitHub
    # status/latest.json was not committed, an ambiguous HTTP result cannot be
    # retried without inspecting the confirmed media_id or WeChat draft list.
    journal_file = (status_dir or Path(profile) / "status") / "draft-attempts" / (article.stem + ".json")
    journal = locate(profile, article, status_dir)
    if article.stem >= "2026-10-11":
        if journal_file.exists():
            # Malformed or empty files are not proof of a safe first attempt.
            if not journal:
                raise ValueError("Invalid durable draft journal; manual review required; NEVER retry draft/add")
            valid_confirmation = (
                journal.get("state") == "confirmed"
                and journal.get("article_sha256") == digest
                and journal.get("article_path") == article.as_posix()
                and bool(journal.get("draft_media_id"))
            )
            if not (valid_confirmation and confirmed):
                raise ValueError(
                    "Draft/add attempt exists in durable journal (state=%s); "
                    "reconcile confirmed receipt, SHA, path and media_id before retry."
                    % journal.get("state")
                )
        elif confirmed:
            raise ValueError(
                "Successful receipt on a post-rollout day lacks durable journal; "
                "manual review required; NEVER retry draft/add."
            )
    elif journal_file.exists() and not journal:
        raise ValueError("Invalid durable draft journal; NEVER retry draft/add")
    elif journal is not None and not confirmed:
        raise ValueError(
            "Draft/add attempt exists in durable journal (state=%s). "
            "Reconcile the WeChat media_id and status first; NEVER retry "
            "an ambiguous non-idempotent API call." % journal.get("state")
        )
    if (last.get("status") == "success"
            and last.get("article_path") == article.as_posix()
            and not confirmed):
        raise ValueError(
            "A successful WeChat draft already exists for this exact archive date, "
            "but its receipt differs. Do not re-publish; reconcile the stored draft "
            "and approved archive snapshot manually."
        )
    if not confirmed:
        try:
            from content_os.editorial_review import check as editorial_check
        except ImportError:
            from editorial_review import check as editorial_check
        review = editorial_check(article.resolve().parents[2], profile, article.stem,
                                 raw.decode("utf-8"))
        if review["status"] == "FAIL":
            raise ValueError("Editorial review required before any upload: " + "; ".join(review["errors"]))
    return {
        "profile": profile,
        "article_path": article.as_posix(),
        "article_sha256": digest,
        "status_path": status_file.as_posix(),
        "should_publish": not confirmed,
        "reason": ("confirmed_journal" if confirmed and article.stem >= "2026-10-11"
                   else "matching_success_receipt" if confirmed
                   else "no_matching_success_receipt"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--article", required=True)
    ap.add_argument("--status-dir", type=Path)
    ap.add_argument("--today-only", action="store_true", help="Never dispatch yesterday archive on schedule/manual rerun")
    args = ap.parse_args()
    try:
        result = inspect(Path(args.article), args.profile, args.status_dir)
        # A daily draft bridge must never publish yesterday's latest archive
        # when today's writing task has not created its new file.
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        if args.today_only and Path(args.article).stem != today:
            result["should_publish"] = False
            result["reason"] = "archive_not_today"
    except (OSError, ValueError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write("should_publish=" + str(result["should_publish"]).lower() + "\n")
            handle.write("reason=" + result["reason"] + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
