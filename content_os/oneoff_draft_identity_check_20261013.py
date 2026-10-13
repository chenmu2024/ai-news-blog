"""One-off READ ONLY WeChat diagnosis for originally confirmed October 13 D/E drafts.
May call /token, /draft/get, /draft/count, /draft/batchget only.
Never writes or creates any WeChat draft.
"""
import hashlib, json, os, sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from pathlib import Path
import requests

PROFILES={"zizhitongjian":("TONGJIAN_WECHAT_APP_ID","TONGJIAN_WECHAT_APP_SECRET"),
          "parenting":("PARENTING_WECHAT_APP_ID","PARENTING_WECHAT_APP_SECRET")}
ROOT="https://api.weixin.qq.com/cgi-bin"

def sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

def inspect(p):
    creds=PROFILES[p]
    appid,secret=[os.environ.get(k,"") for k in creds]
    if not appid or not secret: return {"profile":p,"error":"missing_credentials"}
    prox=os.environ.get("PROXY_URL","").strip()
    s=requests.Session()
    s.trust_env=False
    if prox: s.proxies={"https":prox,"http":prox}
    def call(endpoint, body=None):
        if endpoint=="/token":
            resp=s.get(ROOT+endpoint,params={"grant_type":"client_credential","appid":appid,"secret":secret},timeout=30)
        else:
            resp=s.post(ROOT+endpoint,params={"access_token":token},json=body or {},timeout=45)
        resp.raise_for_status()
        return json.loads(resp.content.decode("utf-8"))
    token=call("/token").get("access_token")
    if not token:return {"profile":p,"error":"token_unavailable"}
    journal=json.loads(Path(f"{p}/status/draft-attempts/2026-10-13.json").read_text())
    receipt=json.loads(Path(f"{p}/status/draft-readback/2026-10-13.json").read_text())
    report={"profile":p,"original_confirmed":journal.get("state")=="confirmed",
            "media_id_matches_readback":journal.get("draft_media_id")==receipt.get("draft_media_id")}
    def summary(item):
        from content_os.public_draft_contract import image_sources
        entries=(item.get("news_item") or []) if isinstance(item,dict) else []
        article=entries[0] if entries else {}
        content=article.get("content") or ""
        return {"title":article.get("title"),"body_sha256":sha(content),
                "body_matches_2026_10_13_receipt":sha(content)==receipt.get("readback_body_sha256"),
                "inline_count":len(image_sources(content)),
                "original_images_same_order":[u.split("?")[0].rsplit("/",1)[0] for u in image_sources(content)]==[u.split("?")[0].rsplit("/",1)[0] for u in journal.get("expected_inline_urls",[])],
                "cover_present":bool(article.get("thumb_media_id"))}
    try:
        got=call("/draft/get",{"media_id":journal["draft_media_id"]})
        report["get_code"]=got.get("errcode",0)
        if not got.get("errcode"): report["original"]=summary(got)
    except Exception as exc:
        report["get_error_type"]=type(exc).__name__
    if report.get("get_code",0)==40007 or "original" not in report:
        try:
            count=call("/draft/count").get("total_count",0)
            report["draft_total_count"]=count
            report["scan_complete"]=count<=500
            rows=[]
            for offset in range(0,min(count,500),20):
                response=call("/draft/batchget",{"offset":offset,"count":20,"no_content":0})
                if response.get("errcode"):report["list_code"]=response["errcode"];break
                for entry in response.get("item",[]):
                    content=entry.get("content",{})
                    articles=content.get("news_item",[]) if isinstance(content,dict) else []
                    if articles and articles[0].get("title")==journal["title"]:
                        rows.append({"media_id_matches_original":entry.get("media_id")==journal.get("draft_media_id"),
                                     "candidate_media_id":entry.get("media_id"),
                                     "summary":summary(content)})
            report["matched_original_title_count"]=len(rows)
            report["original_title_matches"]=rows
        except Exception as exc:
            report["list_error_type"]=type(exc).__name__
    return report

def main():
    for p in PROFILES:
        try: print(json.dumps(inspect(p),ensure_ascii=False))
        except Exception as exc:print(json.dumps({"profile":p,"error_type":type(exc).__name__}))

if __name__=="__main__":main()
