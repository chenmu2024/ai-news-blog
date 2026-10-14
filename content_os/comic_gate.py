"""Fail-closed sequential comic contract for new A-F drafts only.

Metadata is a production assertion, NOT image generation or proof of user consent.
Only applies to newly written articles from 2026-10-14 onward. Never mutates drafts.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import date
from pathlib import Path

FIRST_DAY = date(2026, 10, 14)
ALIASES = {"ai_business": "wechat", "business_story": "business"}
ACCOUNTS = {"qiezhi", "wechat", "business", "zizhitongjian", "parenting", "jingyun"}
MARKER = re.compile(r"<!--\s*COMIC_PACKAGE\s*(\{[^<>]*\})\s*-->", re.S)
IMG = re.compile(r"!\[[^\]]*\]\((https://[^)\s]+)\)")
AI = re.compile(r"<!--\s*AI_SCENE\s*(\{[^<>]*\})\s*-->", re.S)
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
BASE = "https://raw.githubusercontent.com/chenmu2024/ai-news-blog/main/"
ASSET = "content_os/assets/ai-scenes/"
SHOTS = {"long", "medium", "close", "detail", "over_shoulder", "wide", "top_down", "reverse", "two_shot"}

def canonical(profile: str) -> str:
    return ALIASES.get(profile, profile)

def required(profile: str, day: str) -> bool:
    return canonical(profile) in ACCOUNTS and date.fromisoformat(day) >= FIRST_DAY

def body_without_marker(markdown: str) -> str:
    return MARKER.sub("", markdown).strip() + "\n"

def binding_sha256(markdown: str) -> str:
    return hashlib.sha256(body_without_marker(markdown).encode("utf-8")).hexdigest()

def check(profile: str, day: str, markdown: str, *, root: Path | None = None,
          verify_files: bool = False) -> list[str]:
    """Verify manifest, visual continuity metadata, approval binding, image/provenance links.

    For a final production preflight use verify_files=True; also run pre-existing
    image_preflight which verifies actual AI_SCENE image bytes and decoding.
    """
    if not required(profile, day):
        return []
    p = canonical(profile)
    errors: list[str] = []
    found = list(MARKER.finditer(markdown))
    if len(found) != 1:
        return ["comic_package_requires_exactly_one_manifest"]
    try:
        pkg = json.loads(found[0].group(1))
    except (ValueError, TypeError):
        return ["comic_package_invalid_json"]
    if not isinstance(pkg, dict):
        return ["comic_package_must_be_object"]
    if pkg.get("profile") != p or pkg.get("article_date") != day:
        errors.append("comic_package_profile_or_date_mismatch")
    if pkg.get("mode") != "original_sequential_comic":
        errors.append("comic_package_mode_must_be_original_sequential_comic")
    panels = pkg.get("panels")
    if not isinstance(panels, list) or not 10 <= len(panels) <= 16:
        errors.append("comic_storyboard_requires_10_to_16_panels")
        panels = panels if isinstance(panels, list) else []
    panel_ids = set()
    panel_per_strip: dict[int, int] = {}
    sequences = set()
    for idx, panel in enumerate(panels, 1):
        if not isinstance(panel, dict):
            errors.append(f"comic_panel_{idx}_not_object")
            continue
        pid = panel.get("id")
        if not isinstance(pid, str) or not pid or pid in panel_ids:
            errors.append(f"comic_panel_{idx}_invalid_or_duplicate_id")
        panel_ids.add(pid)
        shot = panel.get("shot")
        action = panel.get("visible_action")
        setting = panel.get("setting")
        if shot not in SHOTS or not isinstance(action, str) or len(action.strip()) < 4 or not isinstance(setting, str) or not setting.strip():
            errors.append(f"comic_panel_{idx}_missing_visual_action_shot_or_setting")
        signature = (shot, str(action).strip(), str(setting).strip())
        if signature in sequences:
            errors.append(f"comic_panel_{idx}_repeats_identical_action_shot_setting")
        sequences.add(signature)
        n = panel.get("strip_index")
        if type(n) is not int or n < 0:
            errors.append(f"comic_panel_{idx}_invalid_strip_index")
        else:
            panel_per_strip[n] = panel_per_strip.get(n, 0) + 1
    imgs = pkg.get("images")
    if not isinstance(imgs, list) or not 5 <= len(imgs) <= 9:
        errors.append("comic_package_requires_5_to_9_real_rendered_strips")
        imgs = imgs if isinstance(imgs, list) else []
    if panel_per_strip and (set(panel_per_strip) != set(range(len(imgs))) or
                            any(n < 1 or n > 3 for n in panel_per_strip.values())):
        errors.append("comic_panel_strip_index_must_cover_each_strip_with_1_to_3_panels")
    md_urls = IMG.findall(markdown)
    ai_scene = {}
    for m in AI.finditer(markdown):
        try:
            rec = json.loads(m.group(1))
            if isinstance(rec, dict):
                ai_scene[rec.get("image_url")] = rec
        except (ValueError, TypeError):
            errors.append("comic_invalid_ai_scene_provenance")
    image_urls = []
    seen_digests = set()
    root = (root or Path(__file__).resolve().parents[1]).resolve()
    for idx, item in enumerate(imgs, 1):
        if not isinstance(item, dict):
            errors.append(f"comic_strip_{idx}_not_object")
            continue
        url = item.get("url")
        sha = item.get("sha256")
        image_urls.append(url)
        if not isinstance(url, str) or not url.startswith(BASE):
            errors.append(f"comic_strip_{idx}_invalid_url")
            continue
        relative = url[len(BASE):]
        prefix = f"{ASSET}{p}/{day}/"
        if (not relative.startswith(prefix) or not re.fullmatch(r"[A-Za-z0-9_./-]+",relative)
            or ".." in relative.split("/") or not relative.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))):
            errors.append(f"comic_strip_{idx}_invalid_art_path")
            continue
        if md_urls.count(url) != 1:
            errors.append(f"comic_strip_{idx}_must_occur_once_in_markdown_body")
        if not isinstance(sha, str) or not DIGEST.fullmatch(sha):
            errors.append(f"comic_strip_{idx}_sha256_invalid")
        elif sha in seen_digests:
            errors.append(f"comic_strip_{idx}_duplicate_image_hash")
        seen_digests.add(sha)
        rec = ai_scene.get(url)
        if not isinstance(rec, dict) or rec.get("sha256") != sha or rec.get("synthetic") is not True:
            errors.append(f"comic_strip_{idx}_missing_matching_ai_scene_provenance")
        if verify_files:
            target = (root / relative).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                errors.append(f"comic_strip_{idx}_asset_not_persisted")
            elif isinstance(sha, str) and hashlib.sha256(target.read_bytes()).hexdigest() != sha:
                errors.append(f"comic_strip_{idx}_asset_hash_mismatch")
    if len(set(image_urls)) != len(image_urls):
        errors.append("comic_reused_image_url")
    if set(md_urls) != set(image_urls):
        errors.append("comic_body_images_not_equal_rendered_manifest")
    if set(ai_scene) != set(image_urls):
        errors.append("comic_ai_scene_records_do_not_match_rendered_strips")
    approval = pkg.get("approval")
    if not isinstance(approval, dict):
        approval = {}
    if (approval.get("status") != "approved" or approval.get("by") != "user" or
        approval.get("source") != "chat" or
        not re.search(r"同步草稿|确认同步", str(approval.get("message_text", ""))) or
        not str(approval.get("approved_at", "")).strip()):
        errors.append("comic_user_approval_not_recorded_for_exact_candidate")
    if approval.get("body_sha256") != binding_sha256(markdown):
        errors.append("comic_user_approved_body_hash_mismatch")
    editorial = pkg.get("editorial")
    if not isinstance(editorial, dict) or any(editorial.get(k) is not True for k in
        ("actual_images_seen", "mobile_preview_seen", "fact_review", "humanizer_v4", "originality_review")):
        errors.append("comic_editorial_and_visual_attestation_incomplete")
    if p in {"business", "parenting", "jingyun"} and not any(
        term in markdown for term in ("虚构", "情境演绎", "原创故事")):
        errors.append("comic_scenario_disclosure_missing_in_article")
    return errors
