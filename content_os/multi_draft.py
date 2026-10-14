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
