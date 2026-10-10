"""Update the UNIQUE existing WeChat fashion draft, never create another draft.

Triggered only by an explicit reviewed fashion/revisions/YYYY-MM-DD.md.
The original archive and receipt remain immutable. Fail closed on ambiguous
draft identity or failed validation. No freepublish/sendall/draft/add.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re

import publish_draft as pub
from content_os.image_resilience import prepare_images, strip_image_backup_notes

REVISION = Path(os.environ.get("FASHION_REVISION_PATH", "fashion/revisions/2026-10-10.md"))
ORIGINAL = Path("fashion/archive") / REVISION.name
RECEIPT = Path("fashion/status/latest.json")
REPORT = Path("fashion/status/revisions") / (REVISION.stem + ".json")


def _check_original():
    if REVISION.parent.as_posix() != "fashion/revisions" or not REVISION.is_file():
        raise RuntimeError("Only a reviewed fashion/revisions/YYYY-MM-DD.md is eligible")
    if not ORIGINAL.is_file():
        raise RuntimeError("Original successful archive missing")
    existing = json.loads(RECEIPT.read_text("utf-8"))
    old_raw = ORIGINAL.read_bytes()
    old_title = pub.title_of(ORIGINAL.read_text("utf-8"))
    if (existing.get("status") != "success" or
            existing.get("article_path") != ORIGINAL.as_posix() or
            existing.get("article_sha256") != hashlib.sha256(old_raw).hexdigest() or
            existing.get("title") != old_title):
        raise RuntimeError("Original immutable SHA/title/receipt mismatch; abort update")
    return existing, old_title


def _draft_candidates(token: str, wanted: set[str]) -> dict[str, list[tuple[str, dict]]]:
    matches = {title: [] for title in wanted}
    for offset in range(0, 200, 20):
        response = pub.request_with_proxy(
            "POST", pub.API + "/draft/batchget", params={"access_token": token},
            json={"offset": offset, "count": 20, "no_content": 0}, timeout=45,
        ).json()
        if response.get("errcode", 0) != 0:
            raise RuntimeError("Cannot read existing WeChat drafts: " + str(response.get("errcode")))
        rows = response.get("item") or []
        for row in rows:
            articles = row.get("content", {}).get("news_item", [])
            if len(articles) != 1:
                continue  # Never modify bundled multi-article drafts.
            title = articles[0].get("title")
            if title in matches and row.get("media_id"):
                matches[title].append((row["media_id"], articles[0]))
        if len(rows) < 20:
            break
    return matches


def _identical_revision(article: dict, title: str) -> bool:
    html = article.get("content") or ""
    # Text marker is a natural phrase in the new editorial, not an internal
    # secret. Never accept title-only equality as proof of an update.
    return article.get("title") == title and "最值得复制的不是同款" in html


def _render(token: str, new_md: str, new_title: str):
    cleaned = strip_image_backup_notes(pub.strip_internal_notes(pub.unwrap(new_md)))
    pub._PREPARED_IMAGES.clear()
    pub._PREPARED_IMAGES.update(prepare_images(new_md, "fashion"))
    body = re.sub(r"(?m)^#\s+.+?\s*$", "", cleaned, count=1).lstrip()
    body, _ = pub.replace_cards(body, token)
    body, cover = pub.replace_images(body, token)
    if not cover:
        raise RuntimeError("At least five real celebrity images are required; no fallback")
    cover_id = pub.upload_cover(token, cover[0], cover[1], cover[2])
    return pub.styled_html(body), cover_id


def main():
    existing, old_title = _check_original()
    raw = REVISION.read_bytes()
    markdown = raw.decode("utf-8")
    title = pub.title_of(markdown)
    digest = hashlib.sha256(raw).hexdigest()
    if len(title) > 32 or not title:
        raise RuntimeError("Revised WeChat title must be 1..32 characters")
    if REPORT.exists():
        previous = json.loads(REPORT.read_text("utf-8"))
        if previous.get("status") == "success" and previous.get("revision_sha256") == digest:
            print("[SKIP] Existing confirmed revision; never update again")
            return
        raise RuntimeError("Revision receipt conflict")
    tok = pub.token()
    lookup = _draft_candidates(tok, {old_title, title})
    originals = lookup[old_title]
    revised = lookup[title]
    if len(originals) != 1 or revised:
        if not originals and len(revised) == 1 and _identical_revision(revised[0][1], title):
            media_id = revised[0][0]
            print("[RECOVERY] WeChat already has this revised content; no duplicate update")
        else:
            raise RuntimeError("Cannot uniquely identify original/current draft; must inspect manually")
    else:
        media_id = originals[0][0]
        rendered, cover_id = _render(tok, markdown, title)
        article = {
            "article_type": "news", "title": title, "author": pub.AUTHOR[:16],
            "content": rendered, "content_source_url": "",
            "thumb_media_id": cover_id,
            "need_open_comment": 0, "only_fans_can_comment": 0,
        }
        if not pub.AUTHOR:
            article.pop("author", None)
        result = pub.request_with_proxy(
            "POST", pub.API + "/draft/update", params={"access_token": tok},
            json={"media_id": media_id, "index": 0, "articles": article},
            timeout=90,
        ).json()
        if result.get("errcode") != 0:
            raise RuntimeError("WeChat draft/update returned error: " + str(result.get("errcode")))
    verify = pub.request_with_proxy(
        "POST", pub.API + "/draft/get", params={"access_token": tok},
        json={"media_id": media_id}, timeout=45,
    ).json()
    articles = verify.get("news_item") or []
    if len(articles) != 1 or not _identical_revision(articles[0], title):
        raise RuntimeError("WeChat draft/get failed revised-title/content verification")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "status": "success", "operation": "in_place_draft_update",
        "original_article_path": ORIGINAL.as_posix(),
        "revision_path": REVISION.as_posix(), "revision_title": title,
        "revision_sha256": digest, "draft_media_id": media_id,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "")
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print("[SUCCESS] updated existing fashion draft in place and verified by draft/get")
    print("[SAFE] no draft/add, no broadcast, original archive unchanged")


if __name__ == "__main__":
    main()
