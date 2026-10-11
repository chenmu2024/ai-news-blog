from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MIN_VISUALS = {
    "ai_business": 2,
    "business_story": 2,
    "qiezhi": 2,
    "zizhitongjian": 2,
    "parenting": 4,
    "jingyun": 2,
    "fashion": 5,
}

MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.I)
CARD_RE = re.compile(r"<!--\s*(?:WECHAT_CARD|QIEZHI_CARD)\b", re.I)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True)
    ap.add_argument("--profile", required=True, choices=sorted(MIN_VISUALS))
    ap.add_argument("--json-out")
    args = ap.parse_args()

    p = Path(args.article)
    if not p.exists():
        print(json.dumps({"status":"FAIL","hard_failures":["article not found"]}, ensure_ascii=False))
        return 2

    md = p.read_text(encoding="utf-8")
    markdown_images = len(MARKDOWN_IMAGE_RE.findall(md))
    html_images = len(HTML_IMAGE_RE.findall(md))
    cards = len(CARD_RE.findall(md))
    total = markdown_images + html_images + cards
    required = MIN_VISUALS[args.profile]

    failures = []
    if total < required:
        failures.append(
            f"视觉内容不足：{total} < {required}。每篇公众号文章必须有图片，禁止纯文字稿进入草稿箱。"
        )

    result = {
        "status": "FAIL" if failures else "PASS",
        "profile": args.profile,
        "required_visuals": required,
        "visual_count": total,
        "markdown_images": markdown_images,
        "html_images": html_images,
        "renderable_cards": cards,
        "hard_failures": failures,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")

    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
