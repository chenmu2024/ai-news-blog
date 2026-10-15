"""Per-article identity, separate from calendar day, for multiple approved drafts.

Original daily ID remains YYYY-MM-DD. Further drafts may use YYYY-MM-DD--slug.
Each immutable article ID gets its own archive, editorial approval and journal.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import re

PROFILES = {"qiezhi", "wechat", "business", "zizhitongjian", "parenting", "jingyun", "fashion"}
ID_PATTERN = re.compile(r"(?P<day>\d{4}-\d{2}-\d{2})(?:--(?P<slug>[a-z0-9][a-z0-9-]{0,47}))?\Z")

def validate_article_id(day: str, article_id: str) -> str:
    match = ID_PATTERN.fullmatch(article_id)
    if not match or match.group("day") != day or date.fromisoformat(day).isoformat() != day:
        raise ValueError("article_id must be YYYY-MM-DD or YYYY-MM-DD--safe-slug for the given day")
    if match.group("slug") and match.group("slug").endswith("-"):
        raise ValueError("article_id slug cannot end in a dash")
    return article_id

def get_article_identity(article: Path, profile: str) -> tuple[str, str]:
    if profile not in PROFILES or article.parent.name != "archive" or article.parent.parent.name != profile:
        raise ValueError("Article must be inside the specified profile/archive directory")
    match = ID_PATTERN.fullmatch(article.stem)
    if not match:
        raise ValueError("Archive filename must be YYYY-MM-DD or YYYY-MM-DD--safe-slug.md")
    day = match.group("day")
    validate_article_id(day, article.stem)
    return day, article.stem

def approval_path(root: Path, profile: str, article_id: str) -> Path:
    day = article_id[:10]
    validate_article_id(day, article_id)
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
    return root / "content_os" / "draft-approvals" / profile / (article_id + ".json")

def verify_article_approval(root: Path, profile: str, article_id: str, markdown: str) -> list[str]:
    """All new articles from 2026-10-15 require article-bound human consent.

    A manifest is only an attestation and cannot independently prove a user
    said these words in a chat; the producer must preserve the real approval.
    """
    import hashlib
    import json
    if article_id == article_id[:10] and article_id[:10] < "2026-10-15":
        # Historical daily drafts: do not impose new policy retrospectively.
        return []
    try:
        record = json.loads(approval_path(root, profile, article_id).read_text("utf-8"))
    except (OSError, ValueError, TypeError):
        return ["multi_draft_missing_verified_user_approval_record"]
    if not isinstance(record, dict):
        return ["multi_draft_approval_record_not_object"]
    errors = []
    if record.get("profile") != profile or record.get("article_id") != article_id:
        errors.append("multi_draft_approval_identity_mismatch")
    if record.get("article_sha256") != hashlib.sha256(markdown.encode("utf-8")).hexdigest():
        errors.append("multi_draft_approval_stale_body")
    if (record.get("status") != "approved" or record.get("approved_by") != "user"
        or record.get("source") != "chat" or
        not str(record.get("approved_at") or "").strip() or
        not any(s in str(record.get("user_confirmation") or "") for s in ("创建微信草稿", "同步草稿", "确认同步", "创建到微信公众号草稿箱", "创建到微信草稿箱"))):
        errors.append("multi_draft_explicit_user_permission_missing")
    if record.get("previewed_with_real_images") is not True:
        errors.append("multi_draft_final_visual_preview_not_verified")
    return errors


def verify_extra_approval(root: Path, profile: str, article_id: str, markdown: str) -> list[str]:
    """Backward-compatible alias for the per-article approval gate."""
    return verify_article_approval(root, profile, article_id, markdown)
