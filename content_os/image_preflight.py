"""Fetch and decode EVERY external image before installing optional fonts.

No WeChat credentials or uploads; reuse the publisher's strict image stage.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from image_resilience import prepare_images


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--article", type=Path, required=True)
    args = p.parse_args()
    staged = prepare_images(args.article.read_text(encoding="utf-8"), args.profile)
    print(json.dumps({"status": "PASS", "profile": args.profile,
                      "staged_images": len(staged)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
