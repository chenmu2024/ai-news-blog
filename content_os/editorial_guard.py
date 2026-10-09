"""Conservative editorial title guard for NEW C/E archive drafts only.

Unlike source, quality and image gates this does not measure popularity.
Existing archived success receipts are never modified by this module.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re

ACTIVATION = date(2026, 10, 10)
PROFILE_DIR = {"parenting": "parenting", "business_story": "business"}


def normalize_title(title: str) -> str:
    return re.sub(r"[\s，,。！？!?：:—\-《》【】“”‘’]+", "", title).casefold()


def parenting_template_family(title: str) -> str | None:
    """Catch the repeatedly used 'child issue -> parents should not ...' trope."""
    t = re.sub(r"\s+", "", title)
    if t.startswith("孩子") and re.search(
        r"先别|不要急|问题可能|不只是|(?:父母|家长).{0,14}(?:其实|问错|做错|第一步)",
        t,
    ):
        return "孩子问题—父母先别/反转式劝导"
    if re.search(r"^你越.{1,24}孩子越", t):
        return "你越—孩子越"
    return None


def extract_title(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def assess_editorial_title(
    profile: str,
    article: Path,
    title: str,
    archive_dir: Path | None = None,
) -> dict:
    """Return auditable, non-destructive title checks; pre-activation files bypass."""
    if profile not in PROFILE_DIR:
        return {"status": "SKIP", "reasons": [], "compared": 0}
    try:
        target_day = date.fromisoformat(article.stem)
    except ValueError:
        return {"status": "SKIP", "reasons": [], "compared": 0}
    if target_day < ACTIVATION:
        return {"status": "SKIP", "reasons": [], "compared": 0}
    root = archive_dir if archive_dir is not None else article.parent
    if root.name != "archive" and archive_dir is None:
        return {"status": "SKIP", "reasons": [], "compared": 0}
    recent: list[tuple[date, str]] = []
    for item in root.glob("????-??-??.md"):
        if item.resolve() == article.resolve():
            continue
        try:
            day = date.fromisoformat(item.stem)
            if 0 < (target_day - day).days <= 30:
                prev_title = extract_title(item.read_text(encoding="utf-8"))
                if prev_title:
                    recent.append((day, prev_title))
        except (ValueError, OSError, UnicodeError):
            continue
    recent.sort(key=lambda row: row[0], reverse=True)
    reasons: list[str] = []
    normalized = normalize_title(title)
    if any(normalized == normalize_title(old) for _, old in recent):
        reasons.append("标题与近30天归档完全重复")
    if profile == "parenting":
        family = parenting_template_family(title)
        if family and any(parenting_template_family(old) == family for _, old in recent[:6]):
            reasons.append(f"与近6篇归档重复模板型标题：{family}；请改用教育现实/家庭冲突的不同叙事角度")
    return {
        "status": "FAIL" if reasons else "PASS",
        "reasons": reasons,
        "compared": len(recent),
        "prior_six_titles": [t for _, t in recent[:6]],
        "template_family": parenting_template_family(title) if profile == "parenting" else None,
    }
