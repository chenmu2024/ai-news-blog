from __future__ import annotations
import json, os, requests, sys

APP_ID=os.environ["WECHAT_APP_ID"].strip()
APP_SECRET=os.environ["WECHAT_APP_SECRET"].strip()
PROXY_URL=(os.getenv("PROXY_URL") or "").strip()
API="https://api.weixin.qq.com/cgi-bin"
PROXIES={"http":PROXY_URL,"https":PROXY_URL} if PROXY_URL else None

STALE_MEDIA_IDS=[
    "Ew3n3AUcZRS6Fu5y58VPvR2KPg2OYGOh3H3MDHxNf-WcE-Vp4ONyEcDz21RY9f9Q"
]

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
    failed=[]
    for media_id in STALE_MEDIA_IDS:
        d=req(
            "POST",API+"/draft/delete",
            params={"access_token":tok},
            data=json.dumps({"media_id":media_id}).encode("utf-8"),
            headers={"Content-Type":"application/json; charset=utf-8"},
        ).json()
        if d.get("errcode") not in (0, None):
            failed.append((media_id,d))
            print("[DELETE_FAIL]",media_id,d)
        else:
            print("[DELETED]",media_id)
    if failed:
        raise SystemExit(1)

if __name__=="__main__":
    main()

# trigger-cleanup-v1
