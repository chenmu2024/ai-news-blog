from __future__ import annotations
import json, os, requests

APP_ID=os.environ["WECHAT_APP_ID"].strip()
APP_SECRET=os.environ["WECHAT_APP_SECRET"].strip()
PROXY_URL=(os.getenv("PROXY_URL") or "").strip()
API="https://api.weixin.qq.com/cgi-bin"
PROXIES={"http":PROXY_URL,"https":PROXY_URL} if PROXY_URL else None
MEDIA_ID="qDPeD_MVp5DpmMkoYeFhsO_H0Ad_b1Kt11YrcK0GHkb3tcc2D2Q58JxnWWIDiYJc"

def req(method,url,**kwargs):
    r=requests.request(method,url,proxies=PROXIES,timeout=60,**kwargs)
    r.raise_for_status()
    return r

def token():
    d=req("GET",API+"/token",params={"grant_type":"client_credential","appid":APP_ID,"secret":APP_SECRET}).json()
    if not d.get("access_token"):
        raise RuntimeError(d)
    return d["access_token"]

def main():
    tok=token()
    r=req(
        "POST",API+"/draft/get",
        params={"access_token":tok},
        data=json.dumps({"media_id":MEDIA_ID}).encode("utf-8"),
        headers={"Content-Type":"application/json; charset=utf-8"},
    )
    try:
        d=json.loads(r.content.decode("utf-8"))
    except Exception:
        d=r.json()
    if d.get("errcode"):
        raise RuntimeError(d)
    items=d.get("news_item") or []
    if not items:
        raise RuntimeError("empty draft")
    item=items[0]
    print("[TITLE]",item.get("title",""))
    print("[AUTHOR]",item.get("author",""))
    if item.get("author")!="静筠":
        raise RuntimeError("unexpected author: "+repr(item.get("author")))
    html=str(item.get("content") or "")
    forbidden=["资料来源","图片来源","核验说明","编辑说明","发布说明","内部备注","Content-Type","Markdown"]
    found=[x for x in forbidden if x in html]
    print("[FORBIDDEN_FOUND]",found)
    if found:
        raise RuntimeError("public metadata leaked: "+repr(found))
    print("[VERIFY] PASS")

if __name__=="__main__":
    main()

# trigger-verify-v1
