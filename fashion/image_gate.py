from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

SOURCE_RE = re.compile(r"<!--\s*FASHION_SOURCE\s*(\{[\s\S]*?\})\s*-->", re.S)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
TOPIC_TYPES = {"celebrity", "korean", "japanese", "lookbook", "model"}


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
    warnings: list[str] = []

    topic_type = str(data.get("topic_type") or "").strip()
    if topic_type not in TOPIC_TYPES:
        hard_failures.append("topic_type 无效")

    if not str(data.get("subject") or "").strip():
        hard_failures.append("subject 不能为空")

    images = data.get("images")
    if not isinstance(images, list):
        images = []
    if len(images) < 2:
        hard_failures.append("至少需要 2 张图片")

    body_image_urls = set(IMAGE_RE.findall(md))
    manifest_urls = set()

    for idx, raw in enumerate(images, start=1):
        if not isinstance(raw, dict):
            hard_failures.append(f"images[{idx}] 必须是 object")
            continue

        image_url = str(raw.get("image_url") or "").strip()
        source_page_url = str(raw.get("source_page_url") or "").strip()
        rights = str(raw.get("rights") or "").strip()
        verified = raw.get("verified") is True

        if not valid_http_url(image_url):
            hard_failures.append(f"images[{idx}].image_url 无效")
        else:
            manifest_urls.add(image_url)
            if image_url not in body_image_urls:
                hard_failures.append(f"images[{idx}] 未实际出现在正文")

        if source_page_url and not valid_http_url(source_page_url):
            warnings.append(f"images[{idx}].source_page_url 不是有效 URL")
        if not source_page_url and rights != "ai_generated":
            warnings.append(f"images[{idx}] 缺少来源页，建议补充")
        if not rights:
            warnings.append(f"images[{idx}] 未填写 rights")
        if not verified:
            warnings.append(f"images[{idx}] verified 未标记 true")

    extra_body_images = body_image_urls - manifest_urls
    if extra_body_images:
        hard_failures.append("正文存在未登记到 FASHION_SOURCE 的图片")

    item_claims = data.get("item_claims") or []
    if not isinstance(item_claims, list):
        hard_failures.append("item_claims 必须是 array")
        item_claims = []

    for idx, raw in enumerate(item_claims, start=1):
        if not isinstance(raw, dict):
            hard_failures.append(f"item_claims[{idx}] 必须是 object")
            continue
        if not str(raw.get("claim") or "").strip():
            hard_failures.append(f"item_claims[{idx}].claim 不能为空")
        source_url = str(raw.get("source_url") or "").strip()
        if not valid_http_url(source_url):
            hard_failures.append(f"item_claims[{idx}].source_url 无效")
        if raw.get("verified") is not True:
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
        "image_count": len(images),
        "body_image_count": len(body_image_urls),
        "item_claim_count": len(item_claims),
        "hard_failures": hard_failures,
        "warnings": warnings,
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
