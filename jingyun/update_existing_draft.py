from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

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


def batchget_all(tok: str) -> list[dict]:
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


def draft_rows_by_title(drafts: list[dict], title: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for row in drafts:
        mid = str(row.get("media_id") or "")
        content = row.get("content") or {}
        news = content.get("news_item") or []
        if not mid or not news or not isinstance(news[0], dict):
            continue
        if str(news[0].get("title") or "") == title:
            out.append((mid, news[0]))
    return out


def github_json(path: str) -> dict | None:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        fail("GITHUB_TOKEN/GITHUB_REPOSITORY missing; cannot make draft/add durable")
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    r = requests.get(
        url,
        params={"ref": "main"},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        fail(f"GitHub reservation read failed {r.status_code}: {r.text[:500]}")
    data = r.json()
    raw = base64.b64decode(data["content"]).decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        fail("Revision reservation is not a JSON object")
    value["_github_sha"] = data.get("sha")
    return value


def put_github_json(path: str, value: dict, message: str) -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        fail("GITHUB_TOKEN/GITHUB_REPOSITORY missing; cannot persist reservation")
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    existing = github_json(path)
    payload = {
        "message": message,
        "content": base64.b64encode(
            (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        ).decode("ascii"),
        "branch": "main",
    }
    if existing and existing.get("_github_sha"):
        payload["sha"] = existing["_github_sha"]
    r = requests.put(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        fail(f"GitHub reservation write failed {r.status_code}: {r.text[:500]}")


def reserve_new_draft(article_sha: str, title: str, old_title: str) -> str:
    path = f"{PROFILE}/status/revisions/attempts/{ARTICLE.stem}.json"
    existing = github_json(path)
    if existing:
        state = str(existing.get("state") or "")
        if state == "confirmed" and existing.get("draft_media_id"):
            fail(
                "A confirmed revision draft/add already exists; refuse another add. "
                f"media_id={existing.get('draft_media_id')}"
            )
        fail("A previous revision draft/add attempt exists with unknown outcome; refuse retry")

    now = datetime.now(timezone.utc).isoformat()
    reservation = {
        "state": "attempted",
        "operation": "draft/add",
        "profile": PROFILE,
        "article_path": ARTICLE.as_posix(),
        "article_sha256": article_sha,
        "title": title,
        "original_title_absent_in_batchget": True,
        "new_title_absent_in_batchget": True,
        "original_title": old_title,
        "reserved_at_utc": now,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "safety": "Durable write-ahead reservation before non-idempotent WeChat draft/add.",
    }
    put_github_json(path, reservation, "reserve(jingyun): approved revision draft/add")
    return path


def confirm_new_draft(path: str, article_sha: str, title: str, media_id: str) -> None:
    value = {
        "state": "confirmed",
        "operation": "draft/add",
        "profile": PROFILE,
        "article_path": ARTICLE.as_posix(),
        "article_sha256": article_sha,
        "title": title,
        "draft_media_id": media_id,
        "confirmed_at_utc": datetime.now(timezone.utc).isoformat(),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "safety": "WeChat returned media_id; future runs must not call draft/add again.",
    }
    put_github_json(path, value, "confirm(jingyun): approved revision draft/add")


def verify_existing_new_title(tok: str, media_id: str, title: str, md: str) -> dict:
    draft = publisher.get_draft(tok, media_id)
    items = draft.get("news_item") or []
    if not items or not isinstance(items[0], dict):
        fail("Recovered new-title draft has no readable article")
    item = items[0]
    if str(item.get("title") or "") != title:
        fail("Recovered draft title mismatch")
    body = str(item.get("content") or "")
    plain = html.unescape(re.sub(r"<[^>]+>", "", body))
    anchors = ["有一种购物车，很容易辨认", "自己可以排到最后"]
    missing = [x for x in anchors if x not in plain]
    if missing:
        fail("Recovered new-title draft content does not match approved article")
    image_count = len(re.findall(r"<img\b", body, flags=re.I))
    if image_count < 1:
        fail("Recovered new-title draft has no inline image")
    return {
        "draft_get_verified": True,
        "inline_image_count": image_count,
        "expected_inline_image_count": 1,
        "readback_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


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
        fail("Original draft is not strongly confirmed")
    if journal.get("article_path") != original_archive.as_posix():
        fail("Confirmed journal points to another archive")
    if journal.get("article_sha256") != original_sha:
        fail("Confirmed journal SHA does not match original archive")
    if latest.get("draft_media_id") != journal.get("draft_media_id"):
        fail("latest status media_id disagrees with confirmed journal")
    if latest.get("article_path") != original_archive.as_posix():
        fail("latest status points to another archive")

    journal_media_id = str(journal["draft_media_id"])
    old_title = str(journal.get("title") or "")

    raw_md = ARTICLE.read_text("utf-8")
    md = strip_image_backup_notes(
        publisher.strip_internal_notes(publisher.unwrap(raw_md)),
        profile=PROFILE,
    )
    title = publisher.title_of(md)
    api_title = publisher.wechat_safe_title(title)
    if api_title != title:
        fail("Approved revision title exceeds WeChat limit; refuse silent truncation")

    publisher._PREPARED_IMAGES.clear()
    publisher._PREPARED_IMAGES.update(prepare_images(raw_md, profile=PROFILE))
    if len(publisher._PREPARED_IMAGES) < 1:
        fail("Approved revision has no prepared inline image")

    tok = publisher.token()
    drafts = batchget_all(tok)
    old_matches = draft_rows_by_title(drafts, old_title)
    new_matches = draft_rows_by_title(drafts, api_title)

    if len(old_matches) > 1 or len(new_matches) > 1:
        fail("Multiple exact-title drafts found; manual review required")

    # If the new title already exists, recover instead of performing any write.
    if len(new_matches) == 1:
        media_id = new_matches[0][0]
        proof = verify_existing_new_title(tok, media_id, api_title, md)
        update_result = {"errcode": 0, "errmsg": "already present; no write performed"}
        operation = "recovered-existing"
        resolution_mode = "batchget_already_new_title"
    else:
        body_md = re.sub(r"(?m)^#\s+.+?\s*$", "", md, count=1).lstrip()
        body_md, _ = publisher.replace_cards(body_md, tok)
        body_md, cover = publisher.replace_images(body_md, tok)
        if not cover:
            cover = publisher.make_fallback_cover(api_title)
        cover_id = publisher.upload_cover(tok, cover[0], cover[1], cover[2])
        public_html = publisher.styled_html(body_md)

        if len(old_matches) == 1:
            media_id = old_matches[0][0]
            resolution_mode = "batchget_original_title_match"
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
            after = publisher.get_draft(tok, media_id)
            proof = verify_saved_payload(PROFILE, api_title, media_id, public_html, after)
            operation = "draft/update"
        else:
            # Read-only batchget proved both the stale journal title and the approved
            # new title are absent from the current WeChat draft box. Creating one
            # new draft is therefore not a duplicate. Persist an attempt first.
            article_sha = hashlib.sha256(ARTICLE.read_bytes()).hexdigest()
            reservation_path = reserve_new_draft(article_sha, api_title, old_title)
            payload = {
                "articles": [{
                    "article_type": "news",
                    "title": api_title,
                    "author": publisher.AUTHOR[:16],
                    "content": public_html,
                    "content_source_url": "",
                    "thumb_media_id": cover_id,
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }]
            }
            response = publisher.request_with_proxy(
                "POST",
                publisher.API + "/draft/add",
                params={"access_token": tok},
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=60,
            )
            add_result = decode_wechat_response(response)
            media_id = str(add_result.get("media_id") or "")
            if not media_id:
                fail("WeChat draft/add failed or outcome unknown: " + json.dumps(add_result, ensure_ascii=False))
            # Confirm returned media_id DURABLY before readback.
            confirm_new_draft(reservation_path, article_sha, api_title, media_id)
            after = publisher.get_draft(tok, media_id)
            proof = verify_saved_payload(PROFILE, api_title, media_id, public_html, after)
            update_result = add_result
            operation = "draft/add"
            resolution_mode = "batchget_proved_no_existing_draft"

    article_sha = hashlib.sha256(ARTICLE.read_bytes()).hexdigest()
    receipt = {
        "state": "verified",
        "operation": operation,
        "profile": PROFILE,
        "original_draft_date": ORIGINAL_DAY,
        "original_archive": original_archive.as_posix(),
        "original_title": old_title,
        "journal_draft_media_id": journal_media_id,
        "draft_media_id": media_id,
        "media_id_resolution": resolution_mode,
        "new_title": api_title,
        "approved_article_path": ARTICLE.as_posix(),
        "approved_article_sha256": article_sha,
        "wechat_response": update_result,
        "draft_get_verified": proof.get("draft_get_verified") is True,
        "inline_image_count": proof.get("inline_image_count"),
        "expected_inline_image_count": proof.get("expected_inline_image_count"),
        "readback_body_sha256": proof.get("readback_body_sha256"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "safe_note": "Current WeChat drafts were read via batchget first. No publish/broadcast endpoint was called.",
    }
    out = Path(PROFILE) / "status" / "revisions" / (ARTICLE.stem + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", "utf-8")

    print("[SUCCESS] Approved article is verified in WeChat draft box")
    print("[OPERATION]", operation)
    print("[DRAFT_MEDIA_ID]", media_id)
    print("[READBACK_IMAGES]", proof.get("inline_image_count"))
    print("[SAFE] publish/broadcast endpoints were not called")


if __name__ == "__main__":
    main()
