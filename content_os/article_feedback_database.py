"""Build an evidence-only article feedback database for the seven-account Content OS.

Joins immutable archives, title decisions, editorial/Humanizer evidence and
verified reading feedback. Missing metrics stay null. This module never calls
WeChat and never infers views, likes, shares or open rate.
"""
from __future__ import annotations
import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

try:
    from content_os.reading_feedback import load_jsonl, headline_features
except ImportError:
    from reading_feedback import load_jsonl, headline_features

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Shanghai")
PROFILES=("qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion")
METRICS=("views","likes","shares","comments","open_rate")

def _title(markdown:str)->str:
    m=re.search(r"^# (.+)$",markdown,re.M)
    return m.group(1).strip() if m else ""

def _read_json(path:Path):
    try:return json.loads(path.read_text("utf-8"))
    except (OSError,ValueError,UnicodeError):return {}

def _manual_rows(path:Path)->list[dict]:
    rows=load_jsonl(path)
    for n,row in enumerate(rows,1):
        for key in ("likes","shares","comments"):
            value=row.get(key)
            if value is not None and (type(value) is not int or value<0):
                raise ValueError(f"line {n}: {key} must be non-negative integer or null")
        value=row.get("open_rate")
        if value is not None and (type(value) not in (int,float) or isinstance(value,bool) or not (0<=value<=1)):
            raise ValueError(f"line {n}: open_rate must be number 0..1 or null")
    return rows

def _feedback_index(rows:list[dict])->dict:
    # Append-only input: the latest exact profile/date/title observation wins
    # for each metric only when that field is explicitly present.
    out={}
    for row in rows:
        key=(row["profile"],row["date"],row["title"])
        current=out.setdefault(key,{"sources":[],"notes":[]})
        if row.get("source") and row["source"] not in current["sources"]:
            current["sources"].append(row["source"])
        if isinstance(row.get("note"),str) and row["note"].strip():
            current["notes"].append(row["note"].strip())
        for metric in METRICS:
            if metric in row:
                current[metric]=row.get(metric)
    return out

def _performance_levels(records:list[dict])->None:
    by_profile=defaultdict(list)
    for r in records:
        if type(r["metrics"].get("views")) is int:
            by_profile[r["profile"]].append(r["metrics"]["views"])
    for r in records:
        vals=sorted(by_profile[r["profile"]])
        value=r["metrics"].get("views")
        if type(value) is not int or len(vals)<5:
            r["performance_level"]="insufficient_data"
            continue
        med=median(vals)
        lower=vals[max(0,int((len(vals)-1)*0.25))]
        upper=vals[min(len(vals)-1,int((len(vals)-1)*0.75))]
        if value>=upper and upper>med:
            r["performance_level"]="high"
        elif value<=lower and lower<med:
            r["performance_level"]="low"
        else:
            r["performance_level"]="typical"

def build(root:Path, manual_path:Path|None=None)->dict:
    manual_path=manual_path or root/"content_os/reading-feedback/manual.jsonl"
    manual=_manual_rows(manual_path) if manual_path.exists() else []
    feedback=_feedback_index(manual)
    records=[]
    for profile in PROFILES:
        for archive in sorted((root/profile/"archive").glob("????-??-??.md")):
            day=archive.stem
            body=archive.read_text("utf-8")
            title=_title(body)
            title_ledger=_read_json(root/"content_os/title-decisions"/f"{day}.json")
            t=((title_ledger.get("profiles") or {}).get(profile) or {})
            review=_read_json(root/"content_os/editorial-reviews"/profile/f"{day}.json")
            human=review.get("humanizer") if isinstance(review.get("humanizer"),dict) else {}
            refs=human.get("reference_examples") if isinstance(human.get("reference_examples"),list) else []
            f=feedback.get((profile,day,title),{})
            metrics={k:f.get(k) for k in METRICS}
            roles=sorted({x.get("role") for x in refs if isinstance(x,dict) and isinstance(x.get("role"),str)})
            styles=sorted({x.get("style") for x in refs if isinstance(x,dict) and isinstance(x.get("style"),str)})
            records.append({
                "article_id":f"{profile}:{day}",
                "profile":profile,"date":day,"title":title,
                "topic_key":review.get("topic_key"),
                "humanizer_version":human.get("version"),
                "humanizer_roles":roles,
                "humanizer_reference_styles":styles,
                "humanizer_reference_count":len(refs),
                "headline_features":headline_features(title),
                "title_candidates":t.get("candidates") if isinstance(t.get("candidates"),list) else [],
                "title_basis":t.get("basis") if isinstance(t.get("basis"),list) else [],
                "metrics":metrics,
                "metric_sources":f.get("sources",[]),
                "qualitative_notes":f.get("notes",[]),
                "performance_level":"insufficient_data",
            })
    _performance_levels(records)
    return {
        "generated_at":datetime.now(TZ).isoformat(),
        "schema_version":1,
        "records":records,
        "record_count":len(records),
        "verified_view_records":sum(type(x["metrics"].get("views")) is int for x in records),
        "policy":"Evidence-only join. Missing metrics remain null; performance labels require at least 5 verified view records for that profile."
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=ROOT)
    ap.add_argument("--manual",type=Path)
    ap.add_argument("--output",type=Path,default=ROOT/"content_os/feedback-learning/article_feedback_latest.json")
    a=ap.parse_args()
    report=build(a.root,a.manual)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n","utf-8")
    print(json.dumps({"records":report["record_count"],"verified_view_records":report["verified_view_records"]},ensure_ascii=False))
if __name__=="__main__":main()
