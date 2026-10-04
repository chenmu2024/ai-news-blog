from __future__ import annotations
import json, os, requests

APP_ID=os.environ["WECHAT_APP_ID"].strip()
APP_SECRET=os.environ["WECHAT_APP_SECRET"].strip()
PROXY_URL=(os.getenv("PROXY_URL") or "").strip()
API="https://api.weixin.qq.com/cgi-bin"
PROXIES={"http":PROXY_URL,"https":PROXY_URL} if PROXY_URL else None
MEDIA_ID="Ew3n3AUcZRS6Fu5y58VPvS1j6r592MbceWaoNFapijKssDZlaZK6yl0uBGS33iR6"

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
    d=req(
        "POST",API+"/draft/get",
        params={"access_token":tok},
        data=json.dumps({"media_id":MEDIA_ID}).encode("utf-8"),
        headers={"Content-Type":"application/json; charset=utf-8"},
    ).json()
    if d.get("errcode"):
        raise RuntimeError(d)
    items=d.get("news_item") or []
    html="\n".join(str(x.get("content") or "") for x in items if isinstance(x,dict))
    forbidden=["原典依据","图片来源","Wikimedia Commons","CText","ZZTJ_SOURCE","zh.wikisource.org","ctext.org"]
    found=[x for x in forbidden if x in html]
    print("[TITLE]", items[0].get("title") if items else "")
    print("[FORBIDDEN_FOUND]", found)
    print("[VERIFY]", "PASS" if not found else "FAIL")
    if found:
        raise SystemExit(1)

if __name__=="__main__":
    main()
