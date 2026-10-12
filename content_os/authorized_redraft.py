"""Create one explicitly user-authorized replacement WeChat draft with inline AI imagery.

The normal daily archive and normal draft/add journal remain immutable. This
separate path exists only because the user explicitly requested fresh illustrated
drafts after today's first drafts were already confirmed. No publish API exists
in this module.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from content_os.ai_scene_policy import asset_file
from content_os.draft_journal import _environment,_get,_put
from content_os.publish_readiness import check as readiness_check

PROFILE=os.environ["PROFILE"].strip()
ARTICLE=Path(os.environ["ARTICLE_PATH"])
AUTH_ID=os.environ["AUTHORIZED_REDRAFT_ID"].strip()
ALLOWED={"qiezhi","wechat","business","zizhitongjian","parenting","jingyun"}
AI_RE=re.compile(r"<!--\s*AI_SCENE\s*(\{[^<>]*\})\s*-->",re.S)
MD_IMAGE_RE=re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
WECHAT_CARD_RE=re.compile(r"<!--\s*WECHAT_CARD\s+(.+?)\s*-->",re.S)
QIEZHI_CARD_RE=re.compile(r"<!--\s*QIEZHI_CARD\s+(.+?)\s*-->",re.S)

def fail(msg):
    raise RuntimeError(msg)

def jpath():
    if PROFILE not in ALLOWED or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}",AUTH_ID):
        fail("invalid authorized redraft identity")
    return f"{PROFILE}/status/authorized-redrafts/{AUTH_ID}.json"

def put_retry(token,repo,path,value,sha):
    for attempt in range(6):
        try:
            _put(token,repo,path,value,sha)
            return
        except HTTPError as exc:
            if exc.code not in (409,422,429,500,502,503,504) or attempt==5:
                raise
            time.sleep(1+attempt)
            _current,sha=_get(token,repo,path)

def existing_journal(digest):
    token,repo,_run_id=_environment()
    old,sha=_get(token,repo,jpath())
    if old and old.get("state")=="confirmed" and old.get("article_sha256")==digest and old.get("draft_media_id"):
        return old,sha
    if old:
        fail("authorized redraft has attempted/ambiguous or mismatched state; refuse duplicate draft/add")
    return None,None

def reserve(title,digest):
    token,repo,run_id=_environment()
    old,_sha=_get(token,repo,jpath())
    if old:
        fail("authorized redraft journal appeared before reservation; refuse duplicate")
    value={
        "state":"attempted","profile":PROFILE,"authorization_id":AUTH_ID,
        "article_path":ARTICLE.as_posix(),"article_sha256":digest,
        "title":title,"run_id":run_id,"user_authorized_new_draft":True,
        "reason":"User explicitly requested a new draft with an AI realistic image embedded in the WeChat body."
    }
    put_retry(token,repo,jpath(),value,None)
    print("[AUTHORIZED_REDRAFT] durable intent stored",jpath())

def confirm(media_id,digest,uploaded_urls):
    token,repo,run_id=_environment()
    old,sha=_get(token,repo,jpath())
    if not old or old.get("state")!="attempted" or old.get("run_id")!=run_id:
        fail("missing/conflicting authorized redraft reservation")
    if old.get("article_sha256")!=digest:
        fail("redraft article changed after reservation")
    value=dict(old,state="confirmed",draft_media_id=media_id,
               verified_inline_image_urls=uploaded_urls)
    put_retry(token,repo,jpath(),value,sha)
    print("[AUTHORIZED_REDRAFT] confirmed media_id stored")

def mark_readback_verified(media_id,inline_count,uploaded_urls):
    token,repo,_run_id=_environment()
    old,sha=_get(token,repo,jpath())
    if not old or old.get("state")!="confirmed" or old.get("draft_media_id")!=media_id:
        fail("cannot mark verification without matching confirmed journal")
    value=dict(old,
        draft_get_verified=True,
        draft_get_inline_image_count=inline_count,
        draft_get_verified_at_utc=datetime.now(timezone.utc).isoformat(),
        verified_inline_image_urls=uploaded_urls)
    put_retry(token,repo,jpath(),value,sha)

def request_fn(pub):
    fn=getattr(pub,"request_with_proxy",None) or getattr(pub,"request_wechat",None)
    if not fn:
        fail("publisher has no WeChat request helper")
    return fn

def api_root(pub):
    return getattr(pub,"API",None) or getattr(pub,"WECHAT_API",None)

def get_draft(pub,tok,media_id):
    r=request_fn(pub)("POST",api_root(pub)+"/draft/get",
        params={"access_token":tok},
        data=json.dumps({"media_id":media_id},ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type":"application/json; charset=utf-8"},timeout=60)
    d=r.json()
    if d.get("errcode"):
        fail("draft/get failed: "+str(d))
    return d

def create_draft(pub,tok,title,html,cover_id):
    payload={"articles":[{
        "article_type":"news","title":title,"author":pub.AUTHOR[:16],
        "content":html,"content_source_url":"","thumb_media_id":cover_id,
        "need_open_comment":0,"only_fans_can_comment":0
    }]}
    r=request_fn(pub)("POST",api_root(pub)+"/draft/add",
        params={"access_token":tok},
        data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type":"application/json; charset=utf-8"},timeout=90)
    d=r.json()
    if not d.get("media_id"):
        fail("draft/add failed: "+str(d))
    return d["media_id"]

def verify_source(original):
    m=AI_RE.search(original)
    if not m:
        fail("AI_SCENE provenance missing")
    meta=json.loads(m.group(1))
    if meta.get("profile")!=PROFILE or meta.get("article_date")!="2026-10-12":
        fail("AI_SCENE profile/date mismatch")
    if meta.get("generator")!="openai_image_gen" or not meta.get("generation_id"):
        fail("real image generation provenance required")
    if meta.get("rights")!="ai_created_owned" or meta.get("synthetic") is not True:
        fail("AI ownership/synthetic marker invalid")
    if meta.get("pretends_to_be_real_person_or_record") is not False:
        fail("AI illustration cannot impersonate evidence")
    p=asset_file(meta.get("image_url",""))
    if p is None or not p.is_file():
        fail("persisted AI image asset missing")
    data=p.read_bytes()
    if hashlib.sha256(data).hexdigest()!=meta.get("sha256"):
        fail("AI image SHA256 mismatch")
    from PIL import Image
    from io import BytesIO
    with Image.open(BytesIO(data)) as im:
        im.verify()
    return meta

def expected_body_images(md):
    count=len(MD_IMAGE_RE.findall(md))
    if PROFILE=="qiezhi":
        for raw in QIEZHI_CARD_RE.findall(md):
            try:
                spec=json.loads(raw)
                if str(spec.get("role") or "inline").lower()!="cover":
                    count+=1
            except Exception:
                pass
    else:
        count+=len(WECHAT_CARD_RE.findall(md))
    return max(1,count)

def verify_saved_draft(pub,tok,media_id,uploaded_urls,public_md):
    draft=get_draft(pub,tok,media_id)
    items=draft.get("news_item") or []
    if not items:
        fail("draft/get returned empty news_item")
    actual_author=str(items[0].get("author") or "")
    if actual_author!=pub.AUTHOR[:16]:
        print("[AUTHOR_READBACK_WARNING] WeChat returned author=",repr(actual_author),
              "expected=",repr(pub.AUTHOR[:16]))
    actual="\n".join(str(x.get("content") or "") for x in items if isinstance(x,dict))
    if "AI_SCENE" in actual or "generation_id" in actual:
        fail("internal AI provenance leaked into public draft")
    if "AI原创写实示意图" not in actual:
        fail("AI illustration caption missing from saved WeChat body")
    image_count=len(re.findall(r"<img\b",actual,re.I))
    minimum=expected_body_images(public_md)
    if image_count<minimum:
        fail(f"saved draft image count too low: {image_count} < {minimum}")
    # WeChat normalizes scheme, image resolution and query parameters after save.
    # Match the immutable qpic resource parent path rather than the full URL.
    for url in uploaded_urls:
        path=urlparse(url).path
        fingerprint=path.rsplit("/",1)[0] if "/" in path else path
        if fingerprint and fingerprint not in actual:
            fail("saved draft does not contain the uploaded AI image resource fingerprint")
    mark_readback_verified(media_id,image_count,uploaded_urls)
    print("[WECHAT_INLINE_AI_VERIFY] PASS images=",image_count,"minimum=",minimum)
    return image_count

def main():
    if os.environ.get("CONTENT_OS_USER_AUTHORIZED_REDRAFT")!="1":
        fail("explicit user authorization flag missing")
    if PROFILE not in ALLOWED or not ARTICLE.is_file():
        fail("invalid profile/article")
    pub=importlib.import_module(PROFILE+".publish_draft")
    original=ARTICLE.read_text("utf-8")
    meta=verify_source(original)

    # Readiness needs internal source records (especially ZZTJ_SOURCE), whereas
    # public rendering must strip them. Run the contract check first.
    ready_md=pub.strip_image_backup_notes(pub.unwrap(original))
    ready=readiness_check(PROFILE,ready_md,"2026-10-12")
    if ready["status"]!="PASS":
        fail("publisher readiness failed: "+str(ready["errors"]))
    public_md=pub.strip_internal_notes(ready_md)
    title=pub.wechat_safe_title(pub.title_of(public_md))
    digest=hashlib.sha256(ARTICLE.read_bytes()).hexdigest()

    # If this exact authorized redraft was already created, NEVER call draft/add
    # again. Only read it back and finish verification.
    old,_old_sha=existing_journal(digest)
    if old:
        tok=pub.token()
        urls=list(old.get("verified_inline_image_urls") or [])
        if not urls:
            fail("confirmed redraft lacks recorded inline AI image URL")
        verify_saved_draft(pub,tok,old["draft_media_id"],urls,public_md)
        print("[IDEMPOTENT] existing illustrated draft verified",old["draft_media_id"])
        print("[DRAFT_MEDIA_ID]",old["draft_media_id"])
        return

    staged=pub.prepare_images(original,profile=PROFILE)
    ai_url=meta["image_url"]
    if ai_url not in staged:
        fail("AI image was not decoded/staged by image preflight")
    print("[IMAGE_PREFLIGHT] PASS",ai_url)

    tok=pub.token()
    body_md=re.sub(r"(?m)^#\s+.+?\s*$","",public_md,count=1).lstrip()
    data,mime,ext=staged[ai_url]
    wx_ai_url=pub.upload_body(tok,data,mime,ext)
    body_md=body_md.replace(ai_url,wx_ai_url)
    if wx_ai_url not in body_md:
        fail("failed to bind WeChat-hosted AI image into body")

    if PROFILE=="qiezhi":
        body_md,cover_id=pub.render_and_replace(body_md,tok)
    else:
        body_md,_cards=pub.replace_cards(body_md,tok)
        cover_id=pub.upload_cover(tok,data,mime,ext)
    html=pub.styled_html(body_md)
    if wx_ai_url not in html:
        fail("AI image missing after HTML render")

    reserve(title,digest)
    media_id=create_draft(pub,tok,title,html,cover_id)
    confirm(media_id,digest,[wx_ai_url])
    verify_saved_draft(pub,tok,media_id,[wx_ai_url],public_md)
    print("[SUCCESS]",PROFILE,"new illustrated draft confirmed and read back")
    print("[SAFE] draft only; no publish/broadcast API called")
    print("[DRAFT_MEDIA_ID]",media_id)

if __name__=="__main__":
    main()
