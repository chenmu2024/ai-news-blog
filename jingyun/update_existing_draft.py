from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import publish_draft as publisher
from content_os.image_resilience import prepare_images, strip_image_backup_notes
from content_os.public_draft_contract import decode_wechat_response, verify_saved_payload

ARTICLE = Path(os.environ["ARTICLE_PATH"])
ORIGINAL_DAY = os.environ["ORIGINAL_DRAFT_DATE"]
PROFILE = "jingyun"


def fail(message: str) -> None:
    raise RuntimeError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, dict):
        fail("Expected JSON object: " + str(path))
    return value


def main() -> None:
    if not ARTICLE.is_file():
        fail("Approved revision article missing: " + str(ARTICLE))

    original_archive = Path(PROFILE) / "archive" / f"{ORIGINAL_DAY}.md"
    journal_path = Path(PROFILE) / "status" / "draft-attempts" / f"{ORIGINAL_DAY}.json"
    latest_path = Path(PROFILE) / "status" / "latest.json"

    if not original_archive.is_file() or not journal_path.is_file() or not latest_path.is_file():
        fail("Confirmed original draft evidence is incomplete")

    journal = load_json(journal_path)
    latest = load_json(latest_path)
    original_sha = hashlib.sha256(original_archive.read_bytes()).hexdigest()

    if journal.get("state") != "confirmed" or not journal.get("draft_media_id"):
        fail("Original draft is not strongly confirmed; refuse draft/update")
    if journal.get("article_path") != original_archive.as_posix():
        fail("Confirmed journal points to another archive")
    if journal.get("article_sha256") != original_sha:
        fail("Confirmed journal SHA does not match original archive")
    if latest.get("draft_media_id") != journal.get("draft_media_id"):
        fail("latest status media_id disagrees with confirmed journal")
    if latest.get("article_path") != original_archive.as_posix():
        fail("latest status points to another archive")

    journal_media_id = str(journal["draft_media_id"])

    raw_md = ARTICLE.read_text("utf-8")
    md = strip_image_backup_notes(
        publisher.strip_internal_notes(publisher.unwrap(raw_md)),
        profile=PROFILE,
    )
    title = publisher.title_of(md)
    api_title = publisher.wechat_safe_title(title)
    if api_title != title:
        fail("Approved revision title exceeds WeChat limit; refuse silent truncation")

    # Validate and decode every approved source image before any WeChat write.
    publisher._PREPARED_IMAGES.clear()
    publisher._PREPARED_IMAGES.update(prepare_images(raw_md, profile=PROFILE))
    if len(publisher._PREPARED_IMAGES) < 1:
        fail("Approved revision has no prepared inline image")

    tok = publisher.token()

    # Resolve the CURRENT draft object from WeChat itself. The durable journal can
    # become stale if a draft was manually replaced in the WeChat backend.
    # batchget is read-only and prevents blind draft/add or blind update attempts.
    def batchget_all() -> list[dict]:
        items: list[dict] = []
        offset = 0
        while True:
            payload = {"offset": offset, "count": 20, "no_content": 0}
            resp = publisher.request_with_proxy(
                "POST",
                publisher.API + "/draft/batchget",
                params={"access_token": tok},
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=60,
            )
            data = decode_wechat_response(resp)
            if data.get("errcode") not in (None, 0):
                fail("WeChat draft/batchget failed: " + json.dumps(data, ensure_ascii=False))
            page = data.get("item") or []
            if not isinstance(page, list):
                fail("WeChat draft/batchget returned invalid item list")
            items.extend(x for x in page if isinstance(x, dict))
            total = int(data.get("total_count") or len(items))
            offset += len(page)
            if not page or offset >= total:
                break
            if offset > 500:
                fail("Refuse unbounded WeChat draft pagination")
        return items

    drafts = batchget_all()
    old_title = str(journal.get("title") or "")
    matches: list[tuple[str, dict]] = []
    new_title_matches: list[tuple[str, dict]] = []
    for row in drafts:
        mid = str(row.get("media_id") or "")
        content = row.get("content") or {}
        news = content.get("news_item") or []
        if not mid or not news or not isinstance(news[0], dict):
            continue
        row_title = str(news[0].get("title") or "")
        if row_title == old_title:
            matches.append((mid, news[0]))
        if row_title == api_title:
            new_title_matches.append((mid, news[0]))

    if len(matches) == 1:
        media_id, old_item = matches[0]
        resolution_mode = "batchget_title_match"
    elif len(matches) == 0 and len(new_title_matches) == 1:
        # A previous update may have succeeded after the client lost its response.
        # Do not write again. Read back the one exact title match and record it as
        # already-updated only after content/image verification below.
        media_id, old_item = new_title_matches[0]
        resolution_mode = "batchget_already_new_title"
    elif len(matches) == 0:
        fail(
            "Current WeChat draft list has no exact original-title match; "
            "refuse draft/add or guessing another media_id. "
            f"journal_media_id={journal_media_id!r}, old_title={old_title!r}"
        )
    else:
        fail(f"Multiple WeChat drafts match original title {old_title!r}; manual review required")

    if journal_media_id != media_id:
        print("[RECONCILE] journal media_id is stale; resolved current media_id by exact title")
        print("[STALE_MEDIA_ID]", journal_media_id)
        print("[CURRENT_MEDIA_ID]", media_id)

    body_md = re.sub(r"(?m)^#\s+.+?\s*$", "", md, count=1).lstrip()
    body_md, _ = publisher.replace_cards(body_md, tok)
    body_md, cover = publisher.replace_images(body_md, tok)
    if not cover:
        cover = publisher.make_fallback_cover(api_title)
    cover_id = publisher.upload_cover(tok, cover[0], cover[1], cover[2])
    public_html = publisher.styled_html(body_md)

    payload = {
        "media_id": media_id,
        "index": 0,
        "articles": {
            "article_type": "news",
            "title": api_title,
            "author": publisher.AUTHOR[:16],
            "content": public_html,
            "content_source_url": "",
            "thumb_media_id": cover_id,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        },
    }
    if resolution_mode == "batchget_already_new_title":
        after = publisher.get_draft(tok, media_id)
        proof = verify_saved_payload(PROFILE, api_title, media_id, public_html, after)
        update_result = {"errcode": 0, "errmsg": "already updated; write skipped after batchget reconciliation"}
    else:
        response = publisher.request_with_proxy(
            "POST",
            publisher.API + "/draft/update",
        params={"access_token": tok},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=60,
        )
        update_result = decode_wechat_response(response)
        if update_result.get("errcode") not in (None, 0):
            fail("WeChat draft/update failed: " + json.dumps(update_result, ensure_ascii=False))

        # Official readback of the SAME media_id proves this was an in-place update.
        after = publisher.get_draft(tok, media_id)
        proof = verify_saved_payload(PROFILE, api_title, media_id, public_html, after)

    article_sha = hashlib.sha256(ARTICLE.read_bytes()).hexdigest()
    receipt = {
        "state": "verified",
        "operation": "draft/update",
        "profile": PROFILE,
        "original_draft_date": ORIGINAL_DAY,
        "original_archive": original_archive.as_posix(),
        "original_title": journal.get("title"),
        "journal_draft_media_id": journal_media_id,
        "draft_media_id": media_id,
        "media_id_resolution": resolution_mode,
        "new_title": api_title,
        "approved_article_path": ARTICLE.as_posix(),
        "approved_article_sha256": article_sha,
        "update_response": update_result,
        "draft_get_verified": proof.get("draft_get_verified") is True,
        "inline_image_count": proof.get("inline_image_count"),
        "expected_inline_image_count": proof.get("expected_inline_image_count"),
        "readback_body_sha256": proof.get("readback_body_sha256"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "safe_note": "Resolved the current draft via read-only batchget, then updated that existing draft in place; draft/add and publish/broadcast were not called.",
    }
    out = Path(PROFILE) / "status" / "revisions" / (ARTICLE.stem + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", "utf-8")

    print("[SUCCESS] Existing WeChat draft updated in place")
    print("[DRAFT_MEDIA_ID]", media_id)
    print("[READBACK_IMAGES]", proof.get("inline_image_count"))
    print("[SAFE] draft/add and publish/broadcast were not called")


if __name__ == "__main__":
    main()
