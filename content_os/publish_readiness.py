"""Cheap, offline, fail-closed checks BEFORE image/font/WeChat operations.

Quality/Source/Image/Visual Gates remain independent; this catches mismatch
between article markers and the actual publisher's expected input contract.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

PROFILES = {"qiezhi", "wechat", "business", "zizhitongjian", "parenting", "jingyun", "fashion"}
CARD_RE = re.compile(r"<!--\s*(QIEZHI_CARD|WECHAT_CARD)\s+(.+?)\s*-->", re.S)
IMG_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
BLOCK_RE = re.compile(r"<!--\s*(FASHION_SOURCE|ZZTJ_SOURCE)\s*(\{[\s\S]*?\})\s*-->", re.S)


def check(profile: str, markdown: str) -> dict:
    if profile not in PROFILES:
        raise ValueError("unknown profile: " + profile)
    errors: list[str] = []
    title = next((line[2:].strip() for line in markdown.splitlines()
                  if line.startswith("# ")), "")
    if not title:
        errors.append("missing H1 title")
    if profile == "wechat" and not title.startswith("一家"):
        errors.append("AI channel headline must start with 一家")
    images = IMG_RE.findall(markdown)
    if len(set(images)) != len(images) and profile == "fashion":
        errors.append("fashion images must be distinct")
    roles: list[str] = []
    for match in CARD_RE.finditer(markdown):
        tag, raw = match.groups()
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            if not data.get("title"):
                errors.append(tag + " missing title")
            if tag == "QIEZHI_CARD":
                role = data.get("role")
                roles.append(role)
                if role not in ("cover", "inline"):
                    errors.append("QIEZHI_CARD role must be cover or inline")
                if role == "inline" and not data.get("items"):
                    errors.append("QIEZHI_CARD inline requires items")
            elif not isinstance(data.get("items"), list):
                errors.append("WECHAT_CARD requires items array")
        except (ValueError, TypeError, json.JSONDecodeError):
            errors.append("malformed " + tag + " JSON")
    if profile == "qiezhi":
        if "cover" not in roles or "inline" not in roles:
            errors.append("qiezhi requires both cover and inline QIEZHI_CARD for reliable illustration")
    if profile == "fashion":
        sources = [(m.group(1), m.group(2)) for m in BLOCK_RE.finditer(markdown) if m.group(1) == "FASHION_SOURCE"]
        if len(sources) != 1:
            errors.append("fashion requires one FASHION_SOURCE manifest")
        else:
            try:
                data = json.loads(sources[0][1])
                registered = [entry.get("image_url") for entry in data.get("images", [])]
                if len(images) < 5 or len(set(images)) < 5:
                    errors.append("fashion requires at least five distinct image URLs")
                if len(registered) < 5 or set(images) != set(registered):
                    errors.append("fashion manifest and body photos must correspond")
            except (ValueError, TypeError, AttributeError):
                errors.append("fashion manifest malformed")
    if profile == "zizhitongjian":
        if not any(m.group(1) == "ZZTJ_SOURCE" for m in BLOCK_RE.finditer(markdown)):
            errors.append("missing ZZTJ_SOURCE original-text record")
    if profile != "qiezhi" and not images and not CARD_RE.search(markdown):
        errors.append("zero publisher-renderable image/card")
    return {"status": "FAIL" if errors else "PASS", "profile": profile,
            "title": title, "image_count": len(images), "card_count": len(roles),
            "errors": errors}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True, choices=sorted(PROFILES))
    p.add_argument("--article", type=Path, required=True)
    args = p.parse_args()
    result = check(args.profile, args.article.read_text(encoding="utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
