"""Shared, fail-closed WeChat draft readback and public image-caption policy.

This module only performs POST /draft/get (read-only), never draft/add or publish.
A confirmed draft with a failed readback must be investigated, not resubmitted.
"""
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

PROFILES = ("qiezhi", "wechat", "business", "zizhitongjian",
            "parenting", "jingyun", "fashion")
NO_CAPTION = set(PROFILES) - {"fashion"}
IMG_LINE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$")
CAPTION = re.compile(
    r"^(?:AI(?:原创)?(?:写实)?(?:配图|图片|示意图|场景)|"
    r"配图|图片|图注|图源|图片来源|照片来源|来源说明|"
    r"图[一二三四五六七八九十\d]+|摄影|此图|该图|本图|"
    r"虚构人物|不是真实|AI生成)(?:[\s:：、（(]|$)", re.I
)
METADATA = re.compile(
    r"<!--\s*(?:AI_SCENE|IMAGE_BACKUPS|ZZTJ_SOURCE|FASHION_SOURCE)\b|"
    r"\b(?:generation_id|scene_description|scene_role)\s*[:=]", re.I
)
FORBIDDEN_CAPTIONS = (
    "AI原创写实示意图", "AI配图：", "AI原创配图：",
    "此图为虚构人物", "不是真实肖像", "不是真实历史现场",
)


def strip_figure_captions(markdown: str, profile: str) -> str:
    """Only remove immediately adjacent image captions in A-F public copy."""
    if profile not in NO_CAPTION:
        return markdown
    lines, output, after_picture = markdown.splitlines(keepends=True), [], False
    for line in lines:
        content = line.strip()
        if after_picture:
            if not content:
                output.append(line)
                continue
            unwrapped = content.strip("*_ ").lstrip("> ")
            italic = (content.startswith("*") and content.endswith("*")) or (
                content.startswith("_") and content.endswith("_"))
            if italic or CAPTION.match(unwrapped):
                while output and not output[-1].strip():
                    output.pop()
                after_picture = False
                continue
            after_picture = False
        output.append(line)
        if IMG_LINE.fullmatch(content):
            after_picture = True
    return "".join(output)


class ImageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img":
            values = dict(attrs)
            self.urls.append(values.get("src") or values.get("data-src") or "")


def image_sources(body: str) -> list[str]:
    parser = ImageParser()
    parser.feed(body)
    return parser.urls


def verify_saved_payload(profile: str, title: str, media_id: str,
                         expected_html: str, payload: dict) -> dict:
    """Verify the saved body contains ALL uploaded inline images."""
    if profile not in PROFILES:
        raise ValueError("unknown profile")
    if payload.get("errcode"):
        raise RuntimeError("WeChat draft/get rejected request")
    items = payload.get("news_item") or []
    if not items or not isinstance(items[0], dict):
        raise RuntimeError("WeChat draft/get returned no news_item")
    saved = items[0]
    if saved.get("title") and saved["title"] != title:
        raise RuntimeError("WeChat readback title mismatch")
    actual = str(saved.get("content") or "")
    if not actual or METADATA.search(actual):
        raise RuntimeError("Draft body missing or internal metadata leaked")
    if profile in NO_CAPTION and any(x in html.unescape(actual) for x in FORBIDDEN_CAPTIONS):
        raise RuntimeError("A-F draft contains forbidden AI figure caption")
    expected_urls = image_sources(expected_html)
    actual_urls = image_sources(actual)
    minimum = 5 if profile == "fashion" else 1
    if len(expected_urls) < minimum or len(actual_urls) < len(expected_urls):
        raise RuntimeError("Draft/get inline image count below prepared body")
    if profile == "fashion" and len(set(actual_urls)) < 5:
        raise RuntimeError("Fashion draft missing five distinct inline images")
    for url in expected_urls:
        # WeChat can normalize scheme/size/query but normally preserves qpic path parent.
        path = urlparse(url).path
        parent = path.rsplit("/", 1)[0]
        if len(parent) < 10 or parent not in actual:
            raise RuntimeError("Draft/get lost uploaded inline image fingerprint")
    return {
        "draft_get_verified": True,
        "state": "verified", "profile": profile, "draft_media_id": media_id,
        "inline_image_count": len(actual_urls),
        "expected_inline_image_count": len(expected_urls),
        "readback_body_sha256": hashlib.sha256(actual.encode("utf-8")).hexdigest(),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def verify_and_record(profile: str, article: Path, title: str, media_id: str,
                      body_html: str, token: str, request_fn, api_root: str) -> dict:
    """Read back only; persist proof for the existing status synchronization step."""
    response = request_fn(
        "POST", api_root + "/draft/get",
        params={"access_token": token},
        data=json.dumps({"media_id": media_id}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=60,
    )
    result = verify_saved_payload(profile, title, media_id, body_html, response.json())
    article = Path(article)
    result["article_path"] = article.resolve().relative_to(Path.cwd().resolve()).as_posix()
    result["article_sha256"] = hashlib.sha256(article.read_bytes()).hexdigest()
    result["article_date"] = article.stem
    out = Path(profile) / "status" / "draft-readback" / (article.stem + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Redundant proof channel: all seven bridge workflows already commit visual-gate.json.
    # Prevents partial deployment of a newly added file path from losing the proof.
    visual = Path(profile) / "status" / "visual-gate.json"
    if visual.exists():
        gate = json.loads(visual.read_text(encoding="utf-8"))
        if (gate.get("status") != "PASS" or
            gate.get("article_sha256") != result["article_sha256"] or
            gate.get("article_path") != result["article_path"]):
            raise RuntimeError("Visual gate article binding mismatches WeChat readback")
        gate["wechat_inline_readback"] = result
        visual.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[WECHAT_DRAFT_READBACK] verified", profile, result["inline_image_count"], out)
    return result
