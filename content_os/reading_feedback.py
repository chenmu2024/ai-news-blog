"""Validate and summarize manually supplied WeChat article performance.
This is a fallback for accounts without Datacube permission. It never invents
views. Input JSONL is append-only and may contain qualitative observations.
"""
from __future__ import annotations
import argparse, json, re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Shanghai")
PROFILES={"qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion"}

def headline_features(title:str)->list[str]:
    out=[]
    if re.search(r"[?？]",title): out.append("question")
    if re.search(r"为什么|却|反而|但是|之后|以后|真正|最难",title): out.append("contrast")
    if re.search(r"\d",title): out.append("number")
    if re.search(r"公司|品牌|瑞幸|泡泡玛特|小米|比亚迪|字节|腾讯|阿里",title): out.append("company_or_brand")
    if title.startswith("一家"): out.append("starts_with_一家")
    return out or ["plain"]

def load_jsonl(path:Path)->list[dict]:
    rows=[]
    if not path.exists(): return rows
    for n,line in enumerate(path.read_text("utf-8").splitlines(),1):
        if not line.strip(): continue
        item=json.loads(line)
        if item.get("profile") not in PROFILES: raise ValueError(f"line {n}: bad profile")
        if not item.get("title") or not item.get("date"): raise ValueError(f"line {n}: title/date required")
        views=item.get("views")
        if views is not None and (not isinstance(views,int) or views<0):
            raise ValueError(f"line {n}: views must be non-negative integer or null")
        if not item.get("source"):
            raise ValueError(f"line {n}: source required")
        rows.append(item)
    return rows

def summarize(rows:list[dict])->dict:
    by_profile={p:{"records":0,"numeric_records":0,"avg_views":None,"features":{}} for p in sorted(PROFILES)}
    feat=defaultdict(lambda:defaultdict(list))
    for x in rows:
        p=x["profile"]; by_profile[p]["records"]+=1
        if isinstance(x.get("views"),int):
            by_profile[p]["numeric_records"]+=1
            for f in headline_features(x["title"]): feat[p][f].append(x["views"])
    for p in PROFILES:
        vals=[x["views"] for x in rows if x["profile"]==p and isinstance(x.get("views"),int)]
        by_profile[p]["avg_views"]=round(mean(vals),2) if vals else None
        by_profile[p]["features"]={k:{"count":len(v),"avg_views":round(mean(v),2)} for k,v in feat[p].items()}
    return by_profile

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,default=ROOT/"content_os/reading-feedback/manual.jsonl")
    args=ap.parse_args()
    rows=load_jsonl(args.input)
    report={"generated_at":datetime.now(TZ).isoformat(),"source":"manual_verified_only",
            "records":len(rows),"profiles":summarize(rows),
            "policy":"No missing views are inferred; qualitative records never become numeric metrics."}
    out=ROOT/"content_os/reading-feedback/latest.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n","utf-8")
    print("[READING_FEEDBACK]",report["records"])
if __name__=="__main__":main()
