from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote
from html import unescape
import requests

MARKER_RE = re.compile(r"<!--\s*ZZTJ_SOURCE\s*(\{[\s\S]*?\})\s*-->", re.M)

def fail(msg: str, out: str | None = None) -> int:
    result = {"status": "FAIL", "hard_failures": [msg]}
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload + "\n", encoding="utf-8")
    return 1

def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()

def normalize_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<script[\\s\\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\\s\\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[\\s　]+", "", text)
    text = text.replace("〇", "零")
    return text

def fetch_page(url: str) -> str:
    r = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TongjianSourceGate/1.0)"},
        allow_redirects=True,
    )
    r.raise_for_status()
    return r.text

def fetch_wikisource_text(url: str) -> str:
    parsed = urlparse(url)
    parts = [unquote(x) for x in parsed.path.split("/") if x]
    # Expected forms include /zh-hant/資治通鑑/卷010 or /wiki/資治通鑑/卷010.
    if parts and (parts[0].startswith("zh-") or parts[0] == "wiki"):
        parts = parts[1:]
    title = "/".join(parts)
    if not title:
        raise RuntimeError("无法从 primary_text_url 解析维基文库页名")
    r = requests.get(
        "https://zh.wikisource.org/w/api.php",
        params={
            "action": "parse",
            "page": title,
            "prop": "text",
            "format": "json",
            "formatversion": "2",
            "variant": "zh-hant",
        },
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TongjianSourceGate/1.0)"},
    )
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError("MediaWiki API error: " + str(data["error"]))
    html = ((data.get("parse") or {}).get("text") or "")
    if not html:
        raise RuntimeError("MediaWiki API 未返回正文")
    return normalize_text(html)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    p = Path(args.article)
    if not p.exists():
        return fail("article not found", args.json_out)

    md = p.read_text(encoding="utf-8")
    m = MARKER_RE.search(md)
    if not m:
        return fail("缺少 ZZTJ_SOURCE 原典来源记录", args.json_out)

    try:
        d = json.loads(m.group(1))
    except Exception as e:
        return fail("ZZTJ_SOURCE JSON 无法解析: " + str(e), args.json_out)

    errors = []
    if d.get("work") != "资治通鉴":
        errors.append("work 必须为《资治通鉴》")

    volume = d.get("volume")
    if not isinstance(volume, int) or not (1 <= volume <= 294):
        errors.append("volume 必须是 1–294 的整数")

    if not str(d.get("chronicle") or "").strip():
        errors.append("缺少 chronicle（纪/卷内纪名）")
    if not str(d.get("year") or "").strip():
        errors.append("缺少 year（纪年/公元年份）")

    primary = str(d.get("primary_text_url") or "").strip()
    verify = str(d.get("image_check_url") or "").strip()
    if host(primary) != "zh.wikisource.org":
        errors.append("primary_text_url 必须指向 zh.wikisource.org 固定原文")
    if "/%E5%8D%B7" not in primary and "/卷" not in primary:
        errors.append("primary_text_url 必须指向具体卷页，不能只填《资治通鉴》总目录")
    if host(verify) != "ctext.org":
        errors.append("image_check_url 必须指向 ctext.org 影印复核源")

    if d.get("context_verified") is not True:
        errors.append("context_verified 必须为 true：必须读过事件前后上下文")

    excerpt = re.sub(r"\s+", "", str(d.get("original_excerpt") or ""))
    if len(excerpt) < 20:
        errors.append("original_excerpt 至少需要 20 个汉字，证明本篇实际核对过原文")

    # Live verification: the recorded excerpt must actually appear on the
    # exact Wikisource volume page. This prevents fabricated source metadata.
    if not errors:
        try:
            page_text = fetch_wikisource_text(primary)
            if normalize_text(excerpt) not in page_text:
                errors.append("original_excerpt 未在 primary_text_url 对应的维基文库卷页中找到")
        except Exception as e:
            errors.append("无法在线核验 primary_text_url: " + str(e))

        try:
            verify_html = fetch_page(verify)
            if len(verify_html) < 500:
                errors.append("image_check_url 返回内容异常，无法确认影印复核入口")
        except Exception as e:
            errors.append("无法访问 image_check_url: " + str(e))

    quotes = d.get("direct_quotes")
    if not isinstance(quotes, list):
        errors.append("direct_quotes 必须是数组；无直接引语时使用 []")
        quotes = []
    else:
        for i, item in enumerate(quotes, start=1):
            if not isinstance(item, dict):
                errors.append(f"direct_quotes[{i}] 格式错误")
                continue
            text = re.sub(r"\s+", "", str(item.get("text") or ""))
            if len(text) < 4:
                errors.append(f"direct_quotes[{i}] 引语过短或为空")
            if item.get("verified") is not True:
                errors.append(f"direct_quotes[{i}] 未标记 verified=true")
            # Every declared direct quote must actually appear in the article,
            # ignoring whitespace differences.
            if text and text not in re.sub(r"\s+", "", md):
                errors.append(f"direct_quotes[{i}] 未在正文中找到，来源记录与正文不一致")

    result = {
        "status": "FAIL" if errors else "PASS",
        "work": d.get("work"),
        "volume": volume,
        "chronicle": d.get("chronicle"),
        "year": d.get("year"),
        "primary_text_url": primary,
        "image_check_url": verify,
        "context_verified": d.get("context_verified"),
        "original_excerpt_chars": len(excerpt),
        "direct_quote_count": len(quotes),
        "live_primary_excerpt_check": "PASS" if not any("original_excerpt" in e or "primary_text_url" in e for e in errors) else "FAIL",
        "image_source_reachable": "PASS" if not any("image_check_url" in e for e in errors) else "FAIL",
        "hard_failures": errors,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")

    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
