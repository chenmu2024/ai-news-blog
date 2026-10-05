from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_RIGHTS = {
    "cc0",
    "public_domain",
    "cc_by",
    "licensed_press",
    "brand_editorial_permission",
    "affiliate_feed_permission",
    "user_owned",
    "pexels_license",
}

TOPIC_TYPES = {"celebrity", "korean", "japanese", "lookbook", "model"}

SOURCE_RE = re.compile(
    r"<!--\s*FASHION_SOURCE\s*(\{[\s\S]*?\})\s*-->",
    re.S,
)

IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")


def fail(msg: str) -> None:
    print("[FASHION_IMAGE_GATE] FAIL:", msg)
    raise SystemExit(1)


def valid_http_url(value: str) -> bool:
    try:
        p = urlparse(value)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:
        return False


def load_manifest(md: str) -> dict:
    m = SOURCE_RE.search(md)
    if not m:
        fail("缺少隐藏 FASHION_SOURCE JSON")
    try:
        data = json.loads(m.group(1))
    except Exception as e:
        fail("FASHION_SOURCE JSON 无法解析: " + str(e))
    if not isinstance(data, dict):
        fail("FASHION_SOURCE 必须是 JSON object")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    path = Path(args.article)
    if not path.exists():
        fail("文章不存在: " + str(path))

    md = path.read_text(encoding="utf-8")
    data = load_manifest(md)
    hard_failures: list[str] = []

    topic_type = str(data.get("topic_type") or "").strip()
    if topic_type not in TOPIC_TYPES:
        hard_failures.append("topic_type 必须是 " + ", ".join(sorted(TOPIC_TYPES)))

    subject = str(data.get("subject") or "").strip()
    if not subject:
        hard_failures.append("subject 不能为空")

    images = data.get("images")
    if not isinstance(images, list) or len(images) < 4:
        hard_failures.append("至少需要 4 张已核验图片")
        images = images if isinstance(images, list) else []

    body_image_urls = set(IMAGE_RE.findall(md))
    manifest_urls = set()

    for idx, raw in enumerate(images, start=1):
        if not isinstance(raw, dict):
            hard_failures.append(f"images[{idx}] 必须是 object")
            continue

        image_url = str(raw.get("image_url") or "").strip()
        source_page_url = str(raw.get("source_page_url") or "").strip()
        rights = str(raw.get("rights") or "").strip()
        evidence = str(raw.get("rights_evidence_url") or "").strip()
        verified = raw.get("verified") is True
        attribution_required = raw.get("attribution_required") is True
        attribution_text = str(raw.get("attribution_text") or "").strip()

        if not valid_http_url(image_url):
            hard_failures.append(f"images[{idx}].image_url 无效")
        else:
            manifest_urls.add(image_url)
            if image_url not in body_image_urls:
                hard_failures.append(f"images[{idx}] 未实际出现在正文: {image_url}")

        if not valid_http_url(source_page_url):
            hard_failures.append(f"images[{idx}].source_page_url 无效")

        if rights not in ALLOWED_RIGHTS:
            hard_failures.append(
                f"images[{idx}].rights={rights!r} 不允许；公开可见/官方发布不等于转载许可"
            )

        if rights == "user_owned":
            if evidence not in {"user_confirmed", "owned_by_user"} and not valid_http_url(evidence):
                hard_failures.append(
                    f"images[{idx}] user_owned 必须用 user_confirmed / owned_by_user 或有效证据URL"
                )
        elif not valid_http_url(evidence):
            hard_failures.append(f"images[{idx}].rights_evidence_url 无效")

        if not verified:
            hard_failures.append(f"images[{idx}] verified 必须为 true")

        if rights == "cc_by" and not attribution_required:
            hard_failures.append(f"images[{idx}] CC BY 必须 attribution_required=true")

        if attribution_required:
            if not attribution_text:
                hard_failures.append(f"images[{idx}] 需要署名但 attribution_text 为空")
            elif attribution_text not in md:
                hard_failures.append(f"images[{idx}] 需要署名，但正文未出现 attribution_text")

    extra_body_images = body_image_urls - manifest_urls
    if extra_body_images:
        hard_failures.append(
            "正文存在未登记到 FASHION_SOURCE 的图片: " + ", ".join(sorted(extra_body_images))
        )

    item_claims = data.get("item_claims")
    if item_claims is None:
        item_claims = []
    if not isinstance(item_claims, list):
        hard_failures.append("item_claims 必须是 array")
        item_claims = []

    for idx, raw in enumerate(item_claims, start=1):
        if not isinstance(raw, dict):
            hard_failures.append(f"item_claims[{idx}] 必须是 object")
            continue
        claim = str(raw.get("claim") or "").strip()
        source_url = str(raw.get("source_url") or "").strip()
        verified = raw.get("verified") is True
        if not claim:
            hard_failures.append(f"item_claims[{idx}].claim 不能为空")
        if not valid_http_url(source_url):
            hard_failures.append(f"item_claims[{idx}].source_url 无效")
        if not verified:
            hard_failures.append(f"item_claims[{idx}] verified 必须为 true")

    public_body = re.sub(SOURCE_RE, "", md)
    precise_claim_signal = re.search(
        r"(?:她穿的是|她身上的是|图中(?:这件|这条|这双|这个).{0,12}(?:来自|是|同款)|"
        r"(?:品牌|型号|SKU|货号|售价|价格为)\s*[:：]?|[¥￥]\s*\d+|"
        r"\d+(?:\.\d+)?\s*元\s*(?:售价|价格))",
        public_body,
    )
    if precise_claim_signal and not item_claims:
        hard_failures.append("正文出现品牌/型号/价格等精确单品事实声明，但 item_claims 为空")

    result = {
        "status": "FAIL" if hard_failures else "PASS",
        "topic_type": topic_type,
        "subject": subject,
        "image_count": len(images),
        "body_image_count": len(body_image_urls),
        "item_claim_count": len(item_claims),
        "hard_failures": hard_failures,
    }

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")

    return 1 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
