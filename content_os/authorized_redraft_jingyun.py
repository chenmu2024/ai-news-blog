"""One user-authorized replacement draft for Jingyun with inline AI imagery.

This creates a NEW WeChat draft only when explicitly enabled by the dedicated
workflow. It never publishes/broadcasts and uses its own durable one-off journal,
so normal daily idempotency remains untouched.
"""
from __future__ import annotations
import hashlib, json, os, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import jingyun.publish_draft as pub
from content_os.draft_journal import _environment, _get, _put

ARTICLE=Path(os.environ["ARTICLE_PATH"])
AUTH_ID=(os.environ.get("AUTHORIZED_REDRAFT_ID") or "").strip()
PROFILE="jingyun"

def fail(msg):
    raise RuntimeError(msg)

def journal_path():
    if not AUTH_ID or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in AUTH_ID):
        fail("invalid AUTHORIZED_REDRAFT_ID")
    return f"{PROFILE}/status/authorized-redrafts/{AUTH_ID}.json"

def reserve(title):
    token, repo, run_id=_environment()
    path=journal_path()
    existing,_sha=_get(token,repo,path)
    if existing:
        fail("authorized redraft already attempted; refuse duplicate: "+path)
    raw=ARTICLE.read_bytes()
    intent={
        "state":"attempted","profile":PROFILE,"authorization_id":AUTH_ID,
        "article_path":ARTICLE.as_posix(),
        "article_sha256":hashlib.sha256(raw).hexdigest(),
        "title":title,"run_id":run_id,
        "user_authorized_new_draft":True,
        "reason":"User explicitly requested a regenerated draft with AI image embedded in the article body."
    }
    _put(token,repo,path,intent,None)
    print("[AUTHORIZED_REDRAFT] durable attempted reservation:",path)

def confirm(media_id):
    token,repo,run_id=_environment()
    path=journal_path()
    existing,sha=_get(token,repo,path)
    if not existing or existing.get("run_id")!=run_id or existing.get("state")!="attempted":
        fail("missing/conflicting authorized redraft reservation")
    if existing.get("article_sha256")!=hashlib.sha256(ARTICLE.read_bytes()).hexdigest():
        fail("redraft article changed after reservation")
    value=dict(existing,state="confirmed",draft_media_id=media_id)
    _put(token,repo,path,value,sha)
    print("[AUTHORIZED_REDRAFT] confirmed new draft media_id")

def create_new_draft(tok,title,body,cover_id):
    payload={"articles":[{
        "article_type":"news","title":title,"author":pub.AUTHOR[:16],
        "content":body,"content_source_url":"","thumb_media_id":cover_id,
        "need_open_comment":0,"only_fans_can_comment":0
    }]}
    reserve(title)
    response=pub.request_with_proxy(
        "POST",pub.API+"/draft/add",
        params={"access_token":tok},
        data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type":"application/json; charset=utf-8"},timeout=60)
    data=response.json()
    if not data.get("media_id"):
        fail("new authorized draft failed: "+str(data))
    confirm(data["media_id"])
    return data["media_id"]

def main():
    if os.environ.get("CONTENT_OS_USER_AUTHORIZED_REDRAFT")!="1":
        fail("explicit authorized-redraft environment flag missing")
    if not ARTICLE.is_file():
        fail("article missing: "+str(ARTICLE))
    original=ARTICLE.read_text("utf-8")
    md=pub.strip_image_backup_notes(pub.strip_internal_notes(pub.unwrap(original)))
    title=pub.wechat_safe_title(pub.title_of(md))
    pub._PREPARED_IMAGES.clear()
    pub._PREPARED_IMAGES.update(pub.prepare_images(original,profile=PROFILE))
    print("[IMAGE_PREFLIGHT] staged",len(pub._PREPARED_IMAGES),"inline image(s)")
    tok=pub.token()
    body_md=pub.re.sub(r"(?m)^#\s+.+?\s*$","",md,count=1).lstrip()
    body_md,card_count=pub.replace_cards(body_md,tok)
    body_md,cover=pub.replace_images(body_md,tok)
    if not cover:
        fail("authorized redraft requires a real inline AI image; fallback cover is not enough")
    cover_id=pub.upload_cover(tok,cover[0],cover[1],cover[2])
    media_id=create_new_draft(tok,title,pub.styled_html(body_md),cover_id)
    pub.verify_public_draft(tok,media_id)
    draft=pub.get_draft(tok,media_id)
    html="\n".join(str(x.get("content") or "") for x in draft.get("news_item") or [] if isinstance(x,dict))
    image_count=html.lower().count("<img")
    if image_count < 1:
        fail("WeChat round-trip contains no inline images")
    print("[INLINE_IMAGE_VERIFY] PASS count=",image_count,"cards=",card_count)
    print("[SUCCESS] user-authorized regenerated Jingyun draft saved with inline AI image")
    print("[SAFE] no publish/broadcast API was called")
    print("[DRAFT_MEDIA_ID]",media_id)

if __name__=="__main__":
    main()
