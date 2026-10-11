"""Validate external images before optional font setup and WeChat API use."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from image_resilience import prepare_images, save_prepared_cache
try:
    from content_os.ai_scene_policy import verify_bytes as verify_ai_scene_bytes
except ImportError:
    from ai_scene_policy import verify_bytes as verify_ai_scene_bytes
import re


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--article", type=Path, required=True)
    args = parser.parse_args()
    original = args.article.read_text(encoding="utf-8")
    day = args.article.stem
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        ai_errors = verify_ai_scene_bytes(args.profile, day, original)
        if ai_errors:
            print(json.dumps({"status": "FAIL", "profile": args.profile, "errors": ai_errors}, ensure_ascii=False))
            return 1
    staged = prepare_images(original, args.profile)
    cache_dir = os.environ.get("CONTENT_OS_IMAGE_CACHE_DIR")
    if cache_dir:
        save_prepared_cache(original, args.profile, staged, Path(cache_dir))
    print(json.dumps({"status": "PASS", "profile": args.profile,
                      "staged_images": len(staged)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
