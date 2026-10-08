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
    # Ancient-text sources often differ only in punctuation, whitespace,
    # Unicode quote forms, or editorial numbering. Ignore those for matching.
    text = re.sub(r"[\\s　]+", "", text)
    text = re.sub(r"[，。！？；：、,.!?;:'\"“”‘’「」『』（）()《》〈〉【】\[\]〔〕—…·＊*#|/\\-]+", "", text)
    text = re.sub(r"(?m)^\\d+", "", text)
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

def fetch_wikisource_text(url: str, variant: str = "zh-hant") -> str:
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
            "variant": variant,
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

def fetch_wikisource_wikitext(url: str) -> str:
    parsed = urlparse(url)
    parts = [unquote(x) for x in parsed.path.split("/") if x]
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
            "prop": "wikitext",
            "format": "json",
            "formatversion": "2",
        },
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TongjianSourceGate/1.0)"},
    )
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError("MediaWiki API error: " + str(data["error"]))
    raw = ((data.get("parse") or {}).get("wikitext") or "")
    if not raw:
        raise RuntimeError("MediaWiki API 未返回原始维基文本")
    return normalize_text(raw)


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
    if "chapter=" not in verify:
        errors.append("image_check_url 必须指向 CText 对应具体卷页面，不能只填总库入口")
    # CText inaccessible: explicitly labelled two-edition original-text fallback.
    # Never claim that inaccessible facsimile images were examined.
    fallback = d.get("alternate_verification_mode") == "dual_edition_text_fallback"
    alternate_url = str(d.get("alternate_text_url") or "").strip()
    alternate_excerpt = re.sub(r"\\s+", "", str(d.get("alternate_excerpt") or ""))
    if d.get("image_check_done") is not True and not fallback:
        errors.append("缺少影印核验，且未提供备用的双版本原典核验")
    if fallback:
        if d.get("image_check_done") is True:
            errors.append("不得把未核验的影印标为已完成")
        if host(alternate_url) != "zh.wikisource.org" or "四庫全書本" not in unquote(alternate_url):
            errors.append("alternate_text_url 必须为四库全书本的具体卷")
        if "/%E5%8D%B7" not in alternate_url and "/卷" not in alternate_url:
            errors.append("alternate_text_url 必须是具体卷页")
        if len(alternate_excerpt) < 12:
            errors.append("alternate_excerpt 至少12字")
        if not str(d.get("alternate_access_reason") or "").strip():
            errors.append("须记录不能检查 CText 影印的原因")

    if d.get("context_verified") is not True:
        errors.append("context_verified 必须为 true：必须读过事件前后上下文")

    excerpt = re.sub(r"\s+", "", str(d.get("original_excerpt") or ""))
    if len(excerpt) < 20:
        errors.append("original_excerpt 至少需要 20 个汉字，证明本篇实际核对过原文")

    # Live verification: the recorded excerpt must actually appear on the
    # exact Wikisource volume page. This prevents fabricated source metadata.
    if not errors:
        try:
            excerpt_norm = normalize_text(excerpt)
            page_hant = fetch_wikisource_text(primary, "zh-hant")
            page_hans = fetch_wikisource_text(primary, "zh-hans")
            # MediaWiki parse output can occasionally differ from the rendered
            # volume page because of variant/rendering transforms. Keep the
            # check strict to the exact same volume URL, but allow the rendered
            # page as a second representation of that primary source.
            page_rendered = normalize_text(fetch_page(primary))
            page_wikitext = fetch_wikisource_wikitext(primary)
            if (
                excerpt_norm not in page_hant
                and excerpt_norm not in page_hans
                and excerpt_norm not in page_rendered
                and excerpt_norm not in page_wikitext
            ):
                errors.append("original_excerpt 未在 primary_text_url 对应的维基文库卷页中找到")
        except Exception as e:
            errors.append("无法在线核验 primary_text_url: " + str(e))

        if fallback:
            try:
                second_hant = fetch_wikisource_text(alternate_url, "zh-hant")
                second_hans = fetch_wikisource_text(alternate_url, "zh-hans")
                second_html = normalize_text(fetch_page(alternate_url))
                alternative = normalize_text(alternate_excerpt)
                if alternative not in second_hant and alternative not in second_hans and alternative not in second_html:
                    errors.append("alternate_excerpt 未在四库全书本具体卷中找到")
            except Exception as e:
                errors.append("第二版本原典在线核验失败: " + str(e))
        else:
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
            # Every declared direct quote must appear in the article and in
            # the exact source volume. This prevents a fabricated quote from
            # being marked verified=true only in metadata.
            if text and normalize_text(text) not in normalize_text(md):
                errors.append(f"direct_quotes[{i}] 未在正文中找到，来源记录与正文不一致")
            if text and not any("primary_text_url" in e for e in errors):
                try:
                    q = normalize_text(text)
                    quote_hant = fetch_wikisource_text(primary, "zh-hant")
                    quote_hans = fetch_wikisource_text(primary, "zh-hans")
                    quote_rendered = normalize_text(fetch_page(primary))
                    quote_wikitext = fetch_wikisource_wikitext(primary)
                    if (
                        q not in quote_hant
                        and q not in quote_hans
                        and q not in quote_rendered
                        and q not in quote_wikitext
                    ):
                        errors.append(f"direct_quotes[{i}] 未在对应《资治通鉴》卷页原文中找到")
                except Exception as e:
                    errors.append(f"direct_quotes[{i}] 原文在线核验失败: {e}")

    result = {
        "status": "FAIL" if errors else "PASS",
        "work": d.get("work"),
        "volume": volume,
        "chronicle": d.get("chronicle"),
        "year": d.get("year"),
        "primary_text_url": primary,
        "image_check_url": verify,
        "image_check_done": d.get("image_check_done"),
        "verification_mode": "dual_edition_text_fallback_no_facsimile" if fallback else "facsimile_check",
        "alternate_text_url": alternate_url if fallback else None,
        "alternate_access_reason": d.get("alternate_access_reason") if fallback else None,
        "context_verified": d.get("context_verified"),
        "original_excerpt_chars": len(excerpt),
        "direct_quote_count": len(quotes),
        "live_primary_excerpt_check": "PASS" if not any("original_excerpt" in e or "primary_text_url" in e for e in errors) else "FAIL",
        "image_source_reachable": "NOT_CHECKED_CTEXT_FALLBACK" if fallback else ("PASS" if not any("image_check_url" in e for e in errors) else "FAIL"),
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
