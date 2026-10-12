"""Create exactly one user-authorized replacement WeChat draft with an inline AI image.

Normal archive/draft journals are left untouched. This path exists only because
the user explicitly requested a NEW draft after today's original draft had
already been confirmed. No publish/broadcast endpoint is used.
"""
from __future__ import annotations
import hashlib
import importlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_os.ai_scene_policy import asset_file
from content_os.draft_journal import _environment, _get, _put
from content_os.publish_readiness import check as readiness_check

PROFILE = os.environ["PROFILE"].strip()
ARTICLE = Path(os.environ["ARTICLE_PATH"])
AUTH_ID = os.environ["AUTHORIZED_REDRAFT_ID"].strip()
ALLOWED = {"qiezhi","wechat","business","zizhitongjian","parenting","jingyun"}
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((https://[^)\s]+)\)")
AI_RE = re.compile(r"<!--\s*AI_SCENE\s*(\{[^<>]*\})\s*-->", re.S)

def fail(msg: str):
    raise RuntimeError(msg)

def jpath() -> str:
    if PROFILE not in ALLOWED:
        fail("profile not authorized")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", AUTH_ID):
        fail("invalid authorization id")
    return f"{PROFILE}/status/authorized-redrafts/{AUTH_ID}.json"

def put_retry(token, repo, path, value, sha):
    for attempt in range(6):
        try:
            _put(token, repo, path, value, sha)
            return
        except HTTPError as exc:
            if exc.code not in (409, 422, 429, 500, 502, 503, 504) or attempt == 5:
                raise
            time.sleep(1 + attempt)
            current, current_sha = _get(token, repo, path)
            if current and current.get("state") == "confirmed":
                return
            sha = current_sha

def reserve(title: str, digest: str):
    token, repo, run_id = _environment()
    path = jpath()
    old, _ = _get(token, repo, path)
    if old:
        if (old.get("state") == "confirmed" and old.get("article_sha256") == digest
                and old.get("draft_media_id")):
            return old
        fail("authorized redraft has an earlier attempted/ambiguous state; refuse duplicate")
    value = {
        "state":"attempted","profile":PROFILE,"authorization_id":AUTH_ID,
        "article_path":ARTICLE.as_posix(),"article_sha256":digest,
        "title":title,"run_id":run_id,"user_authorized_new_draft":True,
        "reason":"User explicitly requested a new draft with the AI realistic image embedded in the WeChat body."
    }
    put_retry(token, repo, path, value, None)
    print("[AUTHORIZED_REDRAFT] durable intent stored", path)
    return None

def confirm(media_id: str, digest: str, uploaded_urls: list[str]):
    token, repo, run_id = _environment()
    path = jpath()
    old, sha = _get(token, repo, path)
    if not old or old.get("state") != "attempted" or old.get("run_id") != run_id:
        fail("missing/conflicting authorized redraft reservation")
    if old.get("article_sha256") != digest:
        fail("article changed after authorized reservation")
    value = dict(old, state="confirmed", draft_media_id=media_id,
                 verified_inline_image_urls=uploaded_urls)
    put_retry(token, repo, path, value, sha)
    print("[AUTHORIZED_REDRAFT] confirmed media_id stored")

def request_fn(pub):
    fn = getattr(pub, "request_with_proxy", None) or getattr(pub, "request_wechat", None)
    if not fn:
        fail("publisher has no WeChat request helper")
    return fn

def api_root(pub):
    return getattr(pub, "API", None) or getattr(pub, "WECHAT_API", None)

def get_draft(pub, tok, media_id):
    fn = request_fn(pub)
    r = fn("POST", api_root(pub)+"/draft/get",
           params={"access_token":tok},
           data=json.dumps({"media_id":media_id},ensure_ascii=False).encode("utf-8"),
           headers={"Content-Type":"application/json; charset=utf-8"}, timeout=60)
    d = r.json()
    if d.get("errcode"):
        fail("draft/get failed: "+str(d))
    return d

def create_draft(pub, tok, title, html, cover_id):
    payload={"articles":[{
        "article_type":"news","title":title,"author":pub.AUTHOR[:16],
        "content":html,"content_source_url":"","thumb_media_id":cover_id,
        "need_open_comment":0,"only_fans_can_comment":0
    }]}
    fn=request_fn(pub)
    r=fn("POST",api_root(pub)+"/draft/add",params={"access_token":tok},
         data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
         headers={"Content-Type":"application/json; charset=utf-8"},timeout=90)
    d=r.json()
    if not d.get("media_id"):
        fail("draft/add failed: "+str(d))
    return d["media_id"]

def verify_source(original: str) -> tuple[dict, bytes]:
    m=AI_RE.search(original)
    if not m:
        fail("AI_SCENE provenance missing")
    meta=json.loads(m.group(1))
    if meta.get("profile") != PROFILE or meta.get("article_date") != "2026-10-12":
        fail("AI_SCENE profile/date mismatch")
    if meta.get("generator") != "openai_image_gen" or not meta.get("generation_id"):
        fail("real image generation provenance required")
    if meta.get("rights") != "ai_created_owned" or meta.get("synthetic") is not True:
        fail("AI ownership/synthetic marker invalid")
    if meta.get("pretends_to_be_real_person_or_record") is not False:
        fail("AI illustration cannot impersonate evidence")
    p=asset_file(meta.get("image_url",""))
    if p is None or not p.is_file():
        fail("persisted AI image asset missing")
    data=p.read_bytes()
    if hashlib.sha256(data).hexdigest() != meta.get("sha256"):
        fail("AI image source SHA256 mismatch")
    from PIL import Image
    from io import BytesIO
    with Image.open(BytesIO(data)) as im:
        im.verify()
    return meta,data

def main():
    if os.environ.get("CONTENT_OS_USER_AUTHORIZED_REDRAFT") != "1":
        fail("explicit user authorization flag missing")
    if PROFILE not in ALLOWED or not ARTICLE.is_file():
        fail("invalid profile/article")
    pub=importlib.import_module(PROFILE+".publish_draft")
    original=ARTICLE.read_text("utf-8")
    meta,_source=verify_source(original)
    public_md=pub.strip_image_backup_notes(pub.strip_internal_notes(pub.unwrap(original)))
    ready=readiness_check(PROFILE, public_md, "2026-10-12")
    if ready["status"] != "PASS":
        fail("publisher readiness failed: "+str(ready["errors"]))
    title=pub.wechat_safe_title(pub.title_of(public_md))
    digest=hashlib.sha256(ARTICLE.read_bytes()).hexdigest()

    staged=pub.prepare_images(original, profile=PROFILE)
    ai_url=meta["image_url"]
    if ai_url not in staged:
        fail("AI image was not decoded/staged by image preflight")
    print("[IMAGE_PREFLIGHT] PASS", ai_url)

    tok=pub.token()
    body_md=re.sub(r"(?m)^#\s+.+?\s*$","",public_md,count=1).lstrip()

    # Upload the AI picture first and replace its private repository identity
    # with the actual WeChat-hosted body URL. This URL is later verified by
    # draft/get, proving the AI picture is inside the saved draft itself.
    data,mime,ext=staged[ai_url]
    wx_ai_url=pub.upload_body(tok,data,mime,ext)
    body_md=body_md.replace(ai_url,wx_ai_url)
    if wx_ai_url not in body_md:
        fail("failed to bind uploaded AI image into Markdown body")

    if PROFILE == "qiezhi":
        body_md,cover_id=pub.render_and_replace(body_md,tok)
    else:
        body_md,_cards=pub.replace_cards(body_md,tok)
        cover_id=pub.upload_cover(tok,data,mime,ext)

    html=pub.styled_html(body_md)
    if wx_ai_url not in html:
        fail("AI image URL missing after HTML render")

    existing=reserve(title,digest)
    if existing:
        media_id=existing["draft_media_id"]
        print("[IDEMPOTENT] previously confirmed authorized redraft",media_id)
    else:
        media_id=create_draft(pub,tok,title,html,cover_id)
        confirm(media_id,digest,[wx_ai_url])

    draft=get_draft(pub,tok,media_id)
    items=draft.get("news_item") or []
    if not items:
        fail("draft/get returned empty news_item")
    actual="\n".join(str(x.get("content") or "") for x in items if isinstance(x,dict))
    if wx_ai_url not in actual:
        fail("saved WeChat draft does not contain the uploaded AI body image")
    if "AI_SCENE" in actual or "generation_id" in actual:
        fail("internal AI provenance leaked into public draft")
    if str(items[0].get("author") or "") != pub.AUTHOR[:16]:
        fail("saved draft author mismatch")
    print("[WECHAT_INLINE_AI_VERIFY] PASS",wx_ai_url)
    print("[SUCCESS]",PROFILE,"new illustrated draft confirmed")
    print("[SAFE] draft only; no publish/broadcast API called")
    print("[DRAFT_MEDIA_ID]",media_id)

if __name__=="__main__":
    main()
