"""ONE authorized recovery: create E's missing 2026-10-13 Work-revised draft.

The confirmed original ID is invalid (WeChat 40007) and exhaustive read-only
checks found neither original nor revised E title in drafts or publications.
User explicitly approved creation of ONE new parenting draft only.

Non-idempotent draft/add is protected by a GitHub write-ahead record at a NEW
path. Unknown outcome is NEVER retried automatically. All A/B/C/D/F/G drafts,
archives and their original receipts remain untouched. No public send APIs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content_os.draft_journal import _environment, _get
from content_os.replace_reviewed_drafts import (
    prepared, render, IMAGE, image_key, identical, persist, text,
)
from content_os.public_draft_contract import image_sources

PROFILE = "parenting"
DAY = "2026-10-13"
NEW_PATH = "parenting/status/revisions/2026-10-13-recreated.json"
OLD_PATH = "parenting/status/draft-attempts/2026-10-13.json"
OLD_TITLE = "北京育儿补贴每孩每年3600元，怎么申领"
NEW_TITLE = "北京育儿补贴漏领了？今年还有补申请通道"
API = "https://api.weixin.qq.com/cgi-bin"
MAX_SCAN = 300


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selected_articles(record: dict) -> list[dict]:
    container = record.get("content") or record
    return container.get("news_item", []) if isinstance(container, dict) else []


def relevant_duplicate(article: dict) -> bool:
    title = str(article.get("title") or "")
    body = text(str(article.get("content") or ""))
    return (title in (OLD_TITLE, NEW_TITLE) or
            (bool(re.search(r"北京(?:市)?育儿补贴", title)) and ("首次申请" in body or "补申请" in body)))


def scan(api, params):
    """Scan both draft list and published list. Unknown/incomplete => no add."""
    detail = {}
    for resource in ("/draft", "/freepublish"):
        path = resource + "/batchget"
        try:
            peek = api(path, params=params, json={"offset": 0, "count": 1, "no_content": 1})
        except RuntimeError as exc:
            # Some official-account types return 48001: no freepublish API
            # permission. Never misreport it as a zero published count.
            # The user explicitly approved one new *draft*. The supported
            # draft collection MUST still be exhaustively checked.
            if resource == "/freepublish" and "error code 48001" in str(exc):
                detail[resource] = {
                    "status": "unknown_no_api_permission",
                    "checked": False,
                    "authorization": "user_explicitly_approved_one_new_draft",
                }
                continue
            raise
        n = peek.get("total_count")
        if not isinstance(n, int) or n < 0 or n > MAX_SCAN:
            raise RuntimeError(resource + " collection size invalid or scan cannot be exhaustive")
        hits = []
        for offset in range(0, n, 20):
            page = api(path, params=params, json={"offset": offset, "count": 20, "no_content": 0})
            entries = page.get("item")
            if not isinstance(entries, list):
                raise RuntimeError(resource + " incomplete list; refuse add")
            for entry in entries:
                for article in selected_articles(entry):
                    if relevant_duplicate(article):
                        hits.append({
                            "title": article.get("title"),
                            "matches_missing_original_id": entry.get("media_id") == detail.get("original_media_id"),
                        })
        detail[resource] = {"count": n, "matching_titles": hits}
        if hits:
            raise RuntimeError(resource + " already contains related Beijing parenting draft; refuse add")
    return detail


def fresh_authorization():
    row, md, images, previous = prepared(PROFILE)
    if (row["title"] != NEW_TITLE or len(images) != 3 or
            len(set(sha(p) for p in images.values())) != 3):
        raise RuntimeError("Revised Work package title or three picture identities invalid")
    old = json.loads(Path(OLD_PATH).read_text("utf-8"))
    if (old.get("state") != "confirmed" or old.get("draft_media_id") != previous.get("draft_media_id")
            or old.get("title") != OLD_TITLE):
        raise RuntimeError("Original E confirmed historical journal changed")
    return row, md, images, previous


def execute():
    row, md, images, old = fresh_authorization()
    github_token, repo, run_id = _environment()
    existing, _ = _get(github_token, repo, NEW_PATH)
    if existing:
        # Never repeat draft/add after any prior attempt, including a timed-out call.
        if existing.get("state") != "confirmed" or not existing.get("draft_media_id"):
            raise RuntimeError("Prior write-ahead new draft attempt exists; manual read-only investigation required")
        raise RuntimeError("New E draft has already been created; do not create a duplicate")
    proxy = (os.environ.get("PROXY_URL") or "").strip()
    if not proxy:
        raise RuntimeError("Static WeChat proxy required for authorized account IP")
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": proxy, "https": proxy}
    def api(endpoint, **kwargs):
        r = session.request("GET" if endpoint == "/token" else "POST",
                            API + endpoint, timeout=90, **kwargs)
        r.raise_for_status()
        result = json.loads(r.content.decode("utf-8"))
        if result.get("errcode", 0) != 0:
            raise RuntimeError("WeChat " + endpoint + " error code " + str(result["errcode"]))
        return result

    token = api("/token", params={
        "grant_type": "client_credential",
        "appid": os.environ["PARENTING_WECHAT_APP_ID"],
        "secret": os.environ["PARENTING_WECHAT_APP_SECRET"]})["access_token"]
    params = {"access_token": token}
    try:
        api("/draft/get", params=params, json={"media_id": old["draft_media_id"]})
    except RuntimeError as exc:
        if "error code 40007" not in str(exc):
            raise
    else:
        raise RuntimeError("Original E draft became reachable; do not create another")
    lists = scan(api, params)

    urls = {}
    for name, image in images.items():
        uploaded = api("/media/uploadimg", params=params,
            files={"media": ("reviewed-parenting.jpg", image, "image/jpeg")})["url"]
        image_key(uploaded)
        urls[name] = uploaded
    cover = api("/material/add_material", params={**params, "type": "image"},
                files={"media": ("reviewed-parenting-cover.jpg",
                                  next(iter(images.values())), "image/jpeg")})["media_id"]
    body = render(IMAGE.sub(lambda m: "![" + m[1] + "](" + urls[m[2]] + ")", md))
    if (len(image_sources(body)) != 3 or
            len(set(image_key(u) for u in image_sources(body))) != 3):
        raise RuntimeError("Rendered article missing unique inline pictures")
    # Re-scan immediately before the irreversible /draft/add.
    scan(api, params)
    current, _ = _get(github_token, repo, NEW_PATH)
    if current:
        raise RuntimeError("Concurrent E attempt detected; never call draft/add")

    journal = {
        "state": "attempted",
        "status": "pending",
        "operation": "create_one_new_missing_work_revised_draft",
        "date": DAY,
        "profile": PROFILE,
        "original_invalid_media_id": old["draft_media_id"],
        "article_path": "content_os/revisions/2026-10-13/parenting.md",
        "article_sha256": row["markdown_sha256"],
        "verified_title": NEW_TITLE,
        "expected_html": body,
        "expected_cover": cover,
        "expected_inline_urls": list(urls.values()),
        "expected_images": 3,
        "pre_add_scan": lists,
        "workflow_run_id": run_id,
        "user_authorized_one_new_draft": True,
    }
    # Durable remote write-ahead intent before single non-idempotent request.
    persist(github_token, repo, NEW_PATH, journal)
    article = {
        "article_type": "news",
        "title": NEW_TITLE,
        "author": "陈慕",
        "content": body,
        "content_source_url": "",
        "thumb_media_id": cover,
        "digest": text(body)[:110],
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    # Exactly one HTTP draft/add call. No retries after ambiguous results.
    created = api("/draft/add", params=params,
        data=json.dumps({"articles": [article]}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    media_id = created.get("media_id")
    if not media_id:
        raise RuntimeError("No media_id acknowledged; do not retry without manual inspection")
    journal.update({"state": "confirmed", "status": "pending_readback",
                    "draft_media_id": media_id})
    persist(github_token, repo, NEW_PATH, journal)
    check = api("/draft/get", params=params, json={"media_id": media_id})
    saved = check.get("news_item") or []
    if (len(saved) != 1 or not identical(saved[0], NEW_TITLE, body, cover) or
            len(image_sources(saved[0].get("content") or "")) != 3):
        raise RuntimeError("New E draft created but readback incomplete; do NOT retry add")
    journal.update({"state": "confirmed", "status": "success",
                    "verified_title": saved[0]["title"],
                    "verified_images": 3,
                    "readback_body_sha256": sha(saved[0]["content"].encode("utf-8"))})
    persist(github_token, repo, NEW_PATH, journal)
    print("[VERIFIED] parenting: one new reviewed Work draft confirmed; 3 images; title " + NEW_TITLE)
    print("[SAFE] no other profile changes, no public publication")


if __name__ == "__main__":
    try:
        execute()
    except Exception as exc:
        # Never expose requests internals (tokens/proxy) in logs.
        if isinstance(exc, RuntimeError):
            print("[FAILED]", type(exc).__name__, str(exc))
        else:
            print("[FAILED]", type(exc).__name__, "operation incomplete; inspect durable journal before any retry")
        sys.exit(1)
