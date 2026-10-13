"""Read-only investigation of missing 2026-10-13 E family-policy draft.
Checks existing drafts AND published-article index. Never creates or sends.
"""
import json, os
from pathlib import Path
import requests
from content_os.public_draft_contract import image_sources

BASE="https://api.weixin.qq.com/cgi-bin"
def main():
    appid=os.getenv("PARENTING_WECHAT_APP_ID","")
    secret=os.getenv("PARENTING_WECHAT_APP_SECRET","")
    proxy=os.getenv("PROXY_URL","")
    if not appid or not secret:
        print(json.dumps({"status":"credentials_missing"}));return
    journal=json.loads(Path("parenting/status/draft-attempts/2026-10-13.json").read_text("utf-8"))
    old=journal.get("title","")
    new="北京育儿补贴漏领了？今年还有补申请通道"
    s=requests.Session()
    s.trust_env=False
    if proxy:s.proxies={"https":proxy,"http":proxy}
    def call(name,params,body=None):
        if name=="/token":r=s.get(BASE+name,params=params,timeout=30)
        else:r=s.post(BASE+name,params=params,json=body or {},timeout=45)
        r.raise_for_status()
        return json.loads(r.content.decode("utf-8"))
    token=call("/token",{"grant_type":"client_credential","appid":appid,"secret":secret}).get("access_token")
    if not token:print(json.dumps({"status":"token_unavailable"}));return
    args={"access_token":token}
    output={"original_draft_title":old,"published_matches":[],"checked_at":"2026-10-13"}
    try:
        total=call("/freepublish/batchget",args,{"offset":0,"count":1,"no_content":1}).get("total_count",0)
        output["published_count"]=total
        output["complete_scan"]=total<=300
        for offset in range(0,min(total,300),20):
            items=call("/freepublish/batchget",args,{"offset":offset,"count":20,"no_content":0})
            if items.get("errcode"):
                output["batch_error_code"]=items["errcode"];break
            for record in items.get("item",[]):
                content=record.get("content") or {}
                articles=content.get("news_item",[]) if isinstance(content,dict) else []
                titles=[a.get("title") for a in articles]
                matched=[title for title in titles if title in (old,new)]
                if matched:
                    output["published_matches"].append({"titles":matched,"article_id_present":bool(record.get("article_id"))})
    except Exception as exc:
        output["published_scan_error_type"]=type(exc).__name__
    print(json.dumps(output,ensure_ascii=False))

if __name__=="__main__":main()
