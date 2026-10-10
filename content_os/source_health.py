"""Lightweight public source reachability audit.
No login, cookies, CAPTCHA bypass, scraping, or paid API. Connectivity only;
HTTP success never proves editorial suitability, freshness, rights, or factuality.
"""
from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit, quote
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Shanghai")
UA="ContentOS-SourceHealth/1.0 (+public reachability only)"

def ascii_url(url: str) -> str:
    parts=urlsplit(url)
    path=quote(parts.path, safe="/%:@")
    query=quote(parts.query, safe="=&%:@,+/?")
    fragment=quote(parts.fragment, safe="%:@,+/?")
    return urlunsplit((parts.scheme,parts.netloc.encode("idna").decode("ascii"),path,query,fragment))

def probe(url: str) -> dict:
    target=ascii_url(url)
    req=Request(target,headers={"User-Agent":UA,"Accept":"text/html,application/xml;q=0.9,*/*;q=0.1"})
    try:
        with urlopen(req,timeout=12) as r:
            r.read(2048)
            code=getattr(r,"status",200)
            return {"url":url,"status":"reachable" if 200 <= code < 400 else "http_error",
                    "http_status":code,"final_url":r.geturl(),
                    "content_type":r.headers.get_content_type()}
    except HTTPError as e:
        return {"url":url,"status":"http_error","http_status":e.code,"error":str(e)[:180]}
    except (URLError,TimeoutError,OSError) as e:
        return {"url":url,"status":"unreachable","http_status":None,"error":str(e)[:180]}

def main():
    now=datetime.now(TZ)
    reg=json.loads((ROOT/"content_os/source_registry.json").read_text("utf-8"))
    jobs=[]
    for profile,cfg in reg["profiles"].items():
        for role in ("primary","fallback"):
            for url in cfg.get(role,[]):
                jobs.append((profile,role,url))
    grouped={profile:[] for profile in reg["profiles"]}
    with ThreadPoolExecutor(max_workers=min(6,max(1,len(jobs)))) as pool:
        futures={pool.submit(probe,url):(profile,role,url) for profile,role,url in jobs}
        for future in as_completed(futures):
            profile,role,url=futures[future]
            try:
                row=future.result()
            except Exception as exc:
                row={"url":url,"status":"probe_error","http_status":None,"error":str(exc)[:180]}
            row["role"]=role
            grouped[profile].append(row)
    profiles={}
    for profile,rows in grouped.items():
        rows.sort(key=lambda x:(0 if x["role"]=="primary" else 1,x["url"]))
        profiles[profile]={
            "sources":rows,
            "primary_reachable":any(x["role"]=="primary" and x["status"]=="reachable" for x in rows),
            "fallback_reachable":any(x["role"]=="fallback" and x["status"]=="reachable" for x in rows),
            "note":"Reachability only; content/date/licence/fact checks remain mandatory.",
        }
    report={"date":now.date().isoformat(),"generated_at":now.isoformat(),"profiles":profiles,
            "policy":"No login, paid API, CAPTCHA bypass or authentication attempted."}
    out=ROOT/"content_os/source-health"/f"{now.date().isoformat()}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n","utf-8")
    latest=ROOT/"content_os/source-health/latest.json"
    latest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n","utf-8")
    print("[SOURCE_HEALTH]",{p:(v["primary_reachable"],v["fallback_reachable"]) for p,v in profiles.items()})
if __name__=="__main__":main()
