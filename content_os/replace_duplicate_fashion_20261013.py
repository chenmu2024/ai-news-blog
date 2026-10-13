"""One-time correction of a duplicated Oct 13 G fashion draft.

Never calls /draft/add, freepublish or mass-send. Operates on the SAME already-
verified media_id only after readback confirms the exact prior reviewed Jisoo
revision; write-ahead journal prevents duplicate /draft/update on retries.
"""
import hashlib
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import markdown
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content_os.replace_reviewed_drafts import identical, render, image_key, persist
from content_os.draft_journal import _environment, _get
from content_os.image_resilience import _get_image
from content_os.public_draft_contract import image_sources

ROOT = Path("content_os/revisions/2026-10-13/fashion-fresh-sana")
RECEIPT = "fashion/status/revisions/2026-10-13-fresh-sana.json"
PREVIOUS = "fashion/status/revisions/2026-10-13.json"
TOKEN_URL = "https://api.weixin.qq.com/cgi-bin"
PICTURE = re.compile(r"!\[([^\]]+)\]\((https://commons\.wikimedia\.org/wiki/Special:FilePath/[^)\s]+)\)")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def load():
    metadata = json.loads((ROOT / "sources.json").read_text("utf-8"))
    raw = (ROOT / "fashion.md").read_text("utf-8")
    if (metadata["operation"] != "second_in_place_update_same_draft_media_id" or
        metadata["profile"] != "fashion" or not metadata["no_new_draft"] or
        metadata["previous_revision_receipt"] != PREVIOUS):
        raise RuntimeError("Wrong or unapproved operation")
    photos = metadata["photos"]
    if len(photos) != 5 or len(set(p["filename"] for p in photos)) != 5:
        raise RuntimeError("Five unique photo sources required")
    title = raw.splitlines()[0].removeprefix("# ")
    if title != metadata["title"] or len(title) > 32:
        raise RuntimeError("Title mismatch")
    pairs = PICTURE.findall(raw)
    if len(pairs) != 5 or [p[1] for p in pairs] != [s["image_url"] for s in photos]:
        raise RuntimeError("Five photo order/identity mismatch")
    if any(p["creator"].strip() == "" or not p["source_page_url"].startswith("https://commons.wikimedia.org/wiki/File:") or
           p["license"] not in ("CC BY 3.0","CC BY 4.0") or
           p["license_url"] != "https://creativecommons.org/licenses/by/" + p["license"].split()[-1] + "/" for p in photos):
        raise RuntimeError("Unverified source/credit/license")
    old = json.loads(Path(PREVIOUS).read_text("utf-8"))
    if (old.get("state") != "confirmed" or old.get("status") != "success" or
        old.get("verified_images") != 5 or not old.get("draft_media_id") or
        old.get("verified_title") != "Jisoo五张旧照：领口比“同款”更值得抄"):
        raise RuntimeError("Original confirmed Jisoo replacement receipt missing")
    past_articles = [p.read_text("utf-8") for p in Path("fashion/archive").glob("*.md")]
    if sum("Jisoo" in x for x in past_articles) < 2:
        raise RuntimeError("Prior published Jisoo duplicate not confirmed")
    return metadata, raw, old

def run():
    metadata, raw, old = load()
    gh_token, repo, run_id = _environment()
    receipt, _ = _get(gh_token,repo,RECEIPT)
    media_id = old["draft_media_id"]
    if receipt and (receipt.get("draft_media_id") != media_id or
                    receipt.get("source_sha256") != digest(raw.encode())):
        raise RuntimeError("Another replacement already attempted; stop")
    proxy = os.environ.get("PROXY_URL","").strip()
    if not proxy: raise RuntimeError("Static authorized WeChat proxy required")
    session = requests.Session()
    session.trust_env=False
    session.proxies={"http":proxy,"https":proxy}
    def api(endpoint, **kwargs):
        r=session.request("GET" if endpoint == "/token" else "POST", TOKEN_URL+endpoint,
                          timeout=90,**kwargs)
        r.raise_for_status()
        j=json.loads(r.content.decode("utf-8"))
        if j.get("errcode",0) != 0: raise RuntimeError("WeChat "+endpoint+" rejected with "+str(j["errcode"]))
        return j
    token=api("/token",params={"grant_type":"client_credential",
           "appid":os.environ["FASHION_WECHAT_APP_ID"],
           "secret":os.environ["FASHION_WECHAT_APP_SECRET"]})["access_token"]
    params={"access_token":token}
    def get():
        items=api("/draft/get",params=params,json={"media_id":media_id}).get("news_item") or []
        if len(items)!=1: raise RuntimeError("Expected one existing article")
        return items[0]
    before=get()
    if receipt:
        if not identical(before,receipt["verified_title"],receipt["expected_html"],receipt["expected_cover"]):
            raise RuntimeError("Ambiguous prior /draft/update, cannot safely retry")
        receipt.update(state="confirmed",status="success",verified_images=5)
        persist(gh_token,repo,RECEIPT,receipt)
        print("[VERIFIED] fashion: already matches fresh Sana content; 5 images; original media_id retained")
        return
    if not identical(before,old["verified_title"],old["expected_html"],old["expected_cover"]):
        raise RuntimeError("Current draft does not match last confirmed Jisoo revision: refuse overwrite")
    # Inspect/convert real licensed images before any write to WeChat.
    pictures={}
    for record in metadata["photos"]:
        original=record["image_url"]
        image_bytes, mime, ext=_get_image(original)
        if mime!="image/jpeg" or len(image_bytes)<10000:
            raise RuntimeError("Image download/decode too small")
        pictures[original]=image_bytes
    checksums=[digest(item) for item in pictures.values()]
    if len(set(checksums)) != 5:
        raise RuntimeError("Duplicate image bytes")
    # Reading the exact same media_id immediately before uploads is an external-edit guard.
    if not identical(get(),old["verified_title"],old["expected_html"],old["expected_cover"]):
        raise RuntimeError("Original draft changed while inspecting new images")
    uploaded={}
    for url, data in pictures.items():
        result=api("/media/uploadimg",params=params,
                   files={"media":("fashion-sana.jpg",data,"image/jpeg")})
        uploaded[url]=result["url"]
        image_key(uploaded[url])
    cover=api("/material/add_material",params={**params,"type":"image"},
              files={"media":("fashion-sana-cover.jpg",next(iter(pictures.values())),"image/jpeg")})["media_id"]
    body=render(PICTURE.sub(lambda m: "!["+m[1]+"]("+uploaded[m[2]]+")", raw.split("\n",1)[1]))
    if len(image_sources(body)) != 5:
        raise RuntimeError("Rendered body must include 5 photos")
    # Confirm original still matches the exact verified former revision.
    if not identical(get(),old["verified_title"],old["expected_html"],old["expected_cover"]):
        raise RuntimeError("Original draft changed during image uploads; refuse update")
    state={"state":"attempted","status":"pending","operation":"second_in_place_update_same_draft_media_id",
           "profile":"fashion","draft_media_id":media_id,"original_title":old["verified_title"],
           "verified_title":metadata["title"],"source_sha256":digest(raw.encode()),
           "source_path":(ROOT/"fashion.md").as_posix(),"image_bytes_sha256":checksums,
           "original_backup":before,"expected_html":body,"expected_cover":cover,"workflow_run_id":run_id}
    persist(gh_token,repo,RECEIPT,state)
    kept={k:before[k] for k in ("author","need_open_comment","only_fans_can_comment") if k in before}
    kept.update({"article_type":"news","title":metadata["title"],"content":body,
                 "thumb_media_id":cover,"content_source_url":"",
                 "digest":"Sana 五次公开活动穿搭的真实照片与日常取舍。"})
    # Exactly one non-idempotent update, NEVER automatically retry.
    api("/draft/update",params=params,
        data=json.dumps({"media_id":media_id,"index":0,"articles":kept},ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type":"application/json; charset=utf-8"})
    after=get()
    if not identical(after,metadata["title"],body,cover):
        raise RuntimeError("Sana updated draft did not pass title/text/images/cover readback")
    state.update(state="confirmed",status="success",verified_images=5)
    persist(gh_token,repo,RECEIPT,state)
    print("[VERIFIED] fashion: Sana duplicate-topic replacement; 5 photos; original media_id retained")

if __name__=="__main__":
    try:run()
    except Exception as exc:
        print("[FAILED]",type(exc).__name__,str(exc) if isinstance(exc,RuntimeError) else "failure; inspect journal, no retries")
        sys.exit(1)
