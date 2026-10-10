"""AIHOT-inspired, offline editorial intelligence. No network or paid services.
Input: JSON array of candidates. Output: grouped ranked candidates per profile.
Each input item: profile,title,url,source,published_at,summary,evidence_level,heat_verified,
optional topic, event_id, recent_views, baseline_views.
"""
import argparse, hashlib, json, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher

PROFILES = ("qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion")
STOP = {"的","是","了","一个","为什么","怎么","如何","什么","这","那"}
def normalize(s):
    s=re.sub(r"[^\w\u4e00-\u9fff]+","",str(s or "").lower())
    return s
def similarity(a,b):
    return SequenceMatcher(None,normalize(a),normalize(b)).ratio()
def score(item, historical_titles):
    title=item.get("title","")
    match=max((similarity(title,h) for h in historical_titles),default=0)
    relevance=max(0,min(100,int(item.get("relevance",60))))
    source={"official":100,"expert":75,"media":60,"unknown":25}.get(item.get("evidence_level"),25)
    verified=bool(item.get("heat_verified",False))
    heat=85 if verified else 30
    novelty=round(100*(1-match))
    hook=max(0,min(100,int(item.get("title_hook",50))))
    total=round(.30*relevance+.25*heat+.20*hook+.15*source+.10*novelty,1)
    flags=[]
    if not verified: flags.append("unverified_heat")
    if match>=.82: flags.append("historical_near_duplicate")
    if item.get("profile") in ("qiezhi","zizhitongjian") and not item.get("primary_text_verified"):
        flags.append("primary_text_unverified")
    if not item.get("url"): flags.append("missing_source_url")
    return total,flags

def analyze(items,history):
    groups=defaultdict(list)
    for x in items:
        p=x.get("profile")
        if p not in PROFILES or not x.get("title"): continue
        assigned=None
        for key,group in groups.items():
            if key[0]!=p:continue
            if x.get("event_id") and key[1]==str(x["event_id"]):assigned=key;break
            if similarity(x["title"],group[0]["title"])>=.82:assigned=key;break
        if assigned is None:assigned=(p,str(x.get("event_id") or hashlib.sha256(normalize(x["title"]).encode()).hexdigest()[:12]))
        groups[assigned].append(x)
    out={p:[] for p in PROFILES}
    for (p,key),group in groups.items():
        representative=max(group,key=lambda x:(x.get("evidence_level")=="official",bool(x.get("url"))))
        rank,flags=score(representative,history.get(p,[]))
        sources=sorted({x.get("source","unknown") for x in group})
        if len(sources)<2:flags.append("single_source")
        out[p].append({"event_id":key,"title":representative["title"],"url":representative.get("url"),
            "score":rank,"flags":flags,"independent_sources":sources,"cluster_size":len(group),
            "title_candidates":representative.get("title_candidates",[]),
            "metrics": {"views":representative.get("recent_views"),"baseline_views":representative.get("baseline_views")}})
    for p in PROFILES:out[p].sort(key=lambda x:(-x["score"],x["event_id"]))
    return out

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--input",type=Path,required=True)
    a.add_argument("--history",type=Path)
    a.add_argument("--output",type=Path,required=True)
    args=a.parse_args()
    items=json.loads(args.input.read_text(encoding="utf8"))
    history=json.loads(args.history.read_text(encoding="utf8")) if args.history and args.history.exists() else {}
    if not isinstance(items,list) or not isinstance(history,dict):raise ValueError("invalid input schema")
    result={"generated_at":datetime.now(timezone.utc).isoformat(),"profiles":analyze(items,history)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("ranked",sum(map(len,result["profiles"].values())),"clusters")
if __name__=="__main__":main()
