"""One-off authorized same-media-id update for October 13 Tongjian.

The original live body diverged from the archived readback. Only target a
uniquely identified, still-available original historic story, with a full
readable backup and write-ahead receipt. Never call /draft/add or publish.
"""
import json, os, sys, hashlib
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from content_os.replace_reviewed_drafts import prepared, render, IMAGE, identical, image_key, persist, text
from content_os.draft_journal import _environment, _get
from content_os.public_draft_contract import image_sources

PROFILE="zizhitongjian"
DAY="2026-10-13"
TARGET="zizhitongjian/status/revisions/2026-10-13.json"
API="https://api.weixin.qq.com/cgi-bin"
OLD_TITLE="商鞅徙木立信：司马光真正担心的是什么"

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def fingerprint(current):
    return (current.get("title"),sha(current.get("content","")),
            tuple(image_key(u) for u in image_sources(current.get("content",""))),
            current.get("thumb_media_id"),current.get("author"))

def verify_old(current, journal):
    if current.get("title") != OLD_TITLE:
        raise RuntimeError("Original D draft title modified; refusing to overwrite")
    body=current.get("content","")
    visible=text(body)
    # The updated Work story is about the same verifiable episode, with both
    # quotations and Sima Guang commentary. Other stories are never overwritten.
    mandatory=("商鞅","徙木","法之不行","夫信者")
    if any(term not in visible for term in mandatory):
        raise RuntimeError("D body is not the original verified historical episode")
    urls=image_sources(body)
    if len(urls) != 2 or len(set(image_key(u) for u in urls)) != 2:
        raise RuntimeError("Existing D draft image structure changed")
    if journal.get("title") != OLD_TITLE or journal.get("state")!="confirmed":
        raise RuntimeError("Original D confirmed journal no longer matches")
    return fingerprint(current)

def main():
    row, md, images, journal=prepared(PROFILE)
    gh, repo, run_id=_environment()
    receipt, _=_get(gh,repo,TARGET)
    original_media_id=journal["draft_media_id"]
    if receipt and (receipt.get("draft_media_id")!=original_media_id or
                    receipt.get("revision_sha256")!=row["markdown_sha256"]):
        raise RuntimeError("Existing D replacement receipt conflicts")
    proxy=os.getenv("PROXY_URL","").strip()
    if not proxy: raise RuntimeError("WeChat static proxy required")
    session=requests.Session(); session.trust_env=False
    session.proxies={"http":proxy,"https":proxy}
    def call(endpoint,**kwargs):
        r=session.request("GET" if endpoint=="/token" else "POST",API+endpoint,timeout=90,**kwargs)
        r.raise_for_status()
        d=json.loads(r.content.decode("utf-8"))
        if d.get("errcode",0)!=0:raise RuntimeError("WeChat "+endpoint+" rejected: "+str(d["errcode"]))
        return d
    token=call("/token",params={"grant_type":"client_credential",
             "appid":os.environ["TONGJIAN_WECHAT_APP_ID"],
             "secret":os.environ["TONGJIAN_WECHAT_APP_SECRET"]})["access_token"]
    params={"access_token":token}
    def current():
        articles=call("/draft/get",params=params,json={"media_id":original_media_id}).get("news_item",[])
        if len(articles)!=1:raise RuntimeError("Expected exactly one existing draft")
        return articles[0]
    saved=current()
    if receipt:
        if not identical(saved,row["title"],receipt["expected_html"],receipt["expected_cover"]):
            raise RuntimeError("Ambiguous previous D update; do not call draft/update again")
        receipt.update(state="confirmed",status="success",verified_images=len(images))
        persist(gh,repo,TARGET,receipt)
        print("[VERIFIED] zizhitongjian: already revised, same media_id, 2 images")
        return
    before_fingerprint=verify_old(saved,journal)
    urls={}
    for name,payload in images.items():
        uploaded=call("/media/uploadimg",params=params,
                 files={"media":("zztj-reviewed.jpg",payload,"image/jpeg")})["url"]
        image_key(uploaded)
        urls[name]=uploaded
    cover=call("/material/add_material",params={**params,"type":"image"},
                 files={"media":("zztj-cover.jpg",next(iter(images.values())),"image/jpeg")})["media_id"]
    html=render(IMAGE.sub(lambda m:"!["+m[1]+"]("+urls[m[2]]+")",md))
    if len(image_sources(html))!=len(images):raise RuntimeError("D new inline count mismatch")
    if fingerprint(current())!=before_fingerprint:
        raise RuntimeError("Existing D draft changed while staging; refusing update")
    result={"operation":"in_place_draft_update","state":"attempted","status":"pending",
            "profile":PROFILE,"draft_media_id":original_media_id,
            "original_backup":saved,"original_actual_body_sha256":sha(saved.get("content","")),
            "old_history_sha256":json.loads(Path("zizhitongjian/status/draft-readback/2026-10-13.json").read_text())["readback_body_sha256"],
            "revision_sha256":row["markdown_sha256"],"revision_title":row["title"],
            "expected_html":html,"expected_cover":cover,"workflow_run_id":run_id}
    persist(gh,repo,TARGET,result)
    kept={k:saved[k] for k in ("author","need_open_comment","only_fans_can_comment") if k in saved}
    kept.update({"article_type":"news","title":row["title"],"content":html,
                 "thumb_media_id":cover,"content_source_url":"","digest":text(html)[:110]})
    call("/draft/update",params=params,
         data=json.dumps({"media_id":original_media_id,"index":0,"articles":kept},ensure_ascii=False).encode("utf-8"),
         headers={"Content-Type":"application/json; charset=utf-8"})
    final=current()
    if not identical(final,row["title"],html,cover):raise RuntimeError("Updated D readback mismatch")
    result.update(state="confirmed",status="success",verified_title=final["title"],verified_images=len(images))
    persist(gh,repo,TARGET,result)
    print("[VERIFIED] zizhitongjian: same media_id updated, 2 images, title="+row["title"])

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("[FAILED]",type(exc).__name__,str(exc) if isinstance(exc,RuntimeError) else "operation failed; do not auto retry")
        sys.exit(1)
