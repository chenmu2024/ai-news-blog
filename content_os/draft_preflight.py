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
    return {
        "profile": profile,
        "article_path": article.as_posix(),
        "article_sha256": digest,
        "status_path": status_file.as_posix(),
        "should_publish": not confirmed,
        "reason": "matching_success_receipt" if confirmed else "no_matching_success_receipt",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--article", required=True)
    ap.add_argument("--status-dir", type=Path)
    args = ap.parse_args()
    try:
        result = inspect(Path(args.article), args.profile, args.status_dir)
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
