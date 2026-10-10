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
import requests

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


def _media_id_from_verified_run(success_receipt: dict) -> str:
    """Find exact media_id from the immutable original successful Actions run."""
    token = os.environ.get("GH_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = str(success_receipt.get("workflow_run_id") or "")
    if not token or not re.fullmatch(r"\d+", run_id) or "/" not in repo:
        raise RuntimeError("Cannot securely retrieve original run media_id")
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json"}
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    response = requests.get(url, headers=headers, timeout=25)
    response.raise_for_status()
    media_ids = []
    for job in (response.json().get("jobs") or []):
        if job.get("conclusion") != "success":
            continue
        logurl = f"https://api.github.com/repos/{repo}/actions/jobs/{job['id']}/logs"
        log_response = requests.get(logurl, headers=headers, timeout=30)
        log_response.raise_for_status()
        for line in log_response.text.splitlines():
            m = re.search(r"\[DRAFT_MEDIA_ID\]\s+([^\s]+)", line)
            if m:
                media_ids.append(m.group(1))
    if len(media_ids) != 1:
        raise RuntimeError("Original successful workflow must contain precisely one media_id")
    return media_ids[0]


def _wechat_json(response):
    # The static proxy may label a UTF-8 JSON response as Latin-1.
    # requests.Response.json() then produces mojibake (e.g. æ\x97¥æ\x9c¬).
    # Decode raw wire bytes explicitly, preserving Chinese titles and HTML.
    return json.loads(response.content.decode("utf-8"))


def _get_exact_draft(token: str, media_id: str) -> dict:
    response = pub.request_with_proxy(
        "POST", pub.API + "/draft/get", params={"access_token": token},
        json={"media_id": media_id}, timeout=45,
    )
    response = _wechat_json(response)
    if response.get("errcode", 0) != 0:
        raise RuntimeError("Original media_id no longer resolves to a WeChat draft")
    articles = response.get("news_item") or []
    if len(articles) != 1:
        raise RuntimeError("Original WeChat draft must contain exactly one article")
    return articles[0]


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
    media_id = _media_id_from_verified_run(existing)
    current = _get_exact_draft(tok, media_id)
    if _identical_revision(current, title):
        print("[RECOVERY] Exact original media_id already has revised contents")
    elif (current.get("title") == old_title or (
            "一件西装负责精神" in (current.get("content") or "") and
            "普通人复刻：先看三处" in (current.get("content") or ""))):
        # The original successful Actions media_id is authoritative. A human
        # may have changed only the title in WeChat after upload; two distinct
        # article-body markers still bind this to the immutable original.
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
    else:
        raise RuntimeError("Original media_id draft does not match archived article. "
                           "Actual title: " + repr(current.get("title")) +
                           "; original title: " + repr(old_title) +
                           "; body marker 1: " + str("一件西装负责精神" in (current.get("content") or "")) +
                           "; body marker 2: " + str("普通人复刻：先看三处" in (current.get("content") or "")))
    verify_response = pub.request_with_proxy(
        "POST", pub.API + "/draft/get", params={"access_token": tok},
        json={"media_id": media_id}, timeout=45,
    )
    verify = _wechat_json(verify_response)
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
