"""Require auditable AI-generated realistic scene imagery in every non-fashion article.

This is a production declaration plus an actual image byte/hash check, not
a magic AI-detection classifier. Missing generation provenance fails closed.
Older confirmed drafts are immutable; requirement starts 2026-10-13.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import date
from urllib.parse import urlparse
from urllib.request import Request, urlopen

START = date(2026, 10, 13)
PROFILE_KEYS = {
    "qiezhi": "qiezhi", "wechat": "wechat", "ai_business": "wechat",
    "business": "business", "business_story": "business",
    "zizhitongjian": "zizhitongjian", "parenting": "parenting",
    "jingyun": "jingyun",
}
MARKER = re.compile(r"<!--\s*AI_SCENE\s*(\{[^<>]*\})\s*-->", re.S)
IMAGE = re.compile(r"!\[[^\]]*\]\((https://[^)\s]+)\)")
HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")
GEN = {"openai_image_gen", "local_ai_image_model", "other_verified_ai_generator"}
CONTENT_PREFIX = "content_os/assets/ai-scenes/"
ROOT_URL = "https://raw.githubusercontent.com/chenmu2024/ai-news-blog/main/"


def required(profile: str, day: str) -> bool:
    return profile in PROFILE_KEYS and date.fromisoformat(day) >= START


def check(profile: str, day: str, markdown: str) -> tuple[list[str], list[dict]]:
    if not required(profile, day):
        return [], []
    errors = []
    matches = list(MARKER.finditer(markdown))
    image_urls = set(IMAGE.findall(markdown))
    if not matches:
        return ["ai_scene_missing: at least one real AI scene image (not a card) is required"], []
    records = []
    for idx, match in enumerate(matches, 1):
        try:
            record = json.loads(match.group(1))
        except (ValueError, TypeError):
            errors.append(f"ai_scene_{idx}: invalid JSON")
            continue
        if not isinstance(record, dict):
            errors.append(f"ai_scene_{idx}: object expected")
            continue
        records.append(record)
        raw_url = record.get("image_url")
        expected_profile = PROFILE_KEYS[profile]
        if record.get("profile") != expected_profile:
            errors.append(f"ai_scene_{idx}: wrong profile")
        if record.get("article_date") != day:
            errors.append(f"ai_scene_{idx}: wrong date")
        if record.get("generator") not in GEN or not str(record.get("generation_id") or "").strip():
            errors.append(f"ai_scene_{idx}: actual model/generation_id provenance required")
        if record.get("rights") != "ai_created_owned":
            errors.append(f"ai_scene_{idx}: missing AI image reuse attestation")
        if record.get("synthetic") is not True or record.get("scene_role") != "illustration":
            errors.append(f"ai_scene_{idx}: must label as synthetic illustration, not evidence")
        if len(str(record.get("scene_description") or "").strip()) < 12:
            errors.append(f"ai_scene_{idx}: scene description missing")
        if not isinstance(raw_url, str) or not raw_url.startswith(ROOT_URL):
            errors.append(f"ai_scene_{idx}: must use persisted public GitHub asset URL")
        else:
            target = raw_url[len(ROOT_URL):]
            path_prefix = f"{CONTENT_PREFIX}{expected_profile}/{day}/"
            if not target.startswith(path_prefix) or not target.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                errors.append(f"ai_scene_{idx}: asset path must match profile/date")
            if raw_url not in image_urls:
                errors.append(f"ai_scene_{idx}: image must appear as Markdown image in body")
        digest = record.get("sha256")
        if not isinstance(digest, str) or not HEX_SHA.fullmatch(digest):
            errors.append(f"ai_scene_{idx}: missing real 64-digit source image SHA256")
        if record.get("pretends_to_be_real_person_or_record") is True:
            errors.append(f"ai_scene_{idx}: cannot impersonate evidence or historical document")
    if not records:
        errors.append("ai_scene_no_valid_records")
    return errors, records


def verify_bytes(profile: str, day: str, markdown: str, *, getter=None) -> list[str]:
    """GET actual repo-hosted AI image bytes and require exact original digest.

    No HTTP call occurs when metadata/body binding is already invalid.
    The regular image preflight independently decodes dimensions and JPEG stages.
    """
    errors, records = check(profile, day, markdown)
    if errors or not records:
        return errors
    for idx, record in enumerate(records, 1):
        url = record["image_url"]
        try:
            if getter is None:
                req = Request(url, headers={"User-Agent": "ContentOS-AISceneProof/1.0"})
                with urlopen(req, timeout=25) as response:
                    if response.status != 200:
                        raise ValueError("HTTP status not 200")
                    mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    if mime not in {"image/png", "image/jpeg", "image/webp"}:
                        raise ValueError("not an image media type")
                    data = response.read(14 * 1024 * 1024 + 1)
            else:
                data = getter(url)
            if not isinstance(data, bytes) or not data or len(data) > 14 * 1024 * 1024:
                raise ValueError("invalid image bytes size")
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("asset SHA256 mismatch")
        except Exception as exc:
            errors.append(f"ai_scene_{idx}: persisted image bytes not verified ({type(exc).__name__}: {exc})")
    return errors
