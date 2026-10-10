"""Validate and summarize per-day headline decisions for seven Content OS profiles.

Editorial evidence only: never publishes, edits a draft, or invents performance.
From 2026-10-11 each decision should contain exactly three unique candidate
headlines, the selected headline and a concrete rationale.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Shanghai")
PROFILES=("qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion")

def archive_title(root:Path, profile:str, day:str)->str:
    p=root/profile/"archive"/f"{day}.md"
    try:text=p.read_text("utf-8")
    except OSError:return ""
    m=re.search(r"^# (.+)$",text,re.M)
    return m.group(1).strip() if m else ""

def validate_record(profile:str, rec:dict, expected_title:str)->list[str]:
    errors=[]
    c=rec.get("candidates")
    if not isinstance(c,list) or len(c)!=3 or any(not isinstance(x,str) or not x.strip() for x in (c or [])):
        errors.append("candidates_must_be_exactly_three_nonempty_strings")
        c=[]
    if c and len({x.strip() for x in c})!=3:
        errors.append("candidate_titles_must_be_unique")
    selected=rec.get("selected_title")
    if not isinstance(selected,str) or not selected.strip():
        errors.append("selected_title_missing")
    elif c and selected not in c:
        errors.append("selected_title_not_in_candidates")
    if expected_title and selected!=expected_title:
        errors.append("selected_title_does_not_match_archive")
    rationale=rec.get("rationale")
    if not isinstance(rationale,str) or len(rationale.strip())<12:
        errors.append("rationale_too_short")
    basis=rec.get("basis")
    if not isinstance(basis,list) or not basis or any(not isinstance(x,str) or not x.strip() for x in basis):
        errors.append("basis_must_be_nonempty_string_list")
    # These fields must describe evidence, not imply unavailable metrics.
    if rec.get("verified_views") is not None and (not isinstance(rec.get("verified_views"),int) or rec["verified_views"]<0):
        errors.append("verified_views_must_be_nonnegative_integer_or_null")
    return errors

def evaluate(root:Path, day:str)->dict:
    path=root/"content_os/title-decisions"/f"{day}.json"
    try:data=json.loads(path.read_text("utf-8"))
    except (OSError,ValueError):
        data={}
    records=data.get("profiles") if isinstance(data,dict) else {}
    if not isinstance(records,dict):records={}
    out={}
    complete=0
    for p in PROFILES:
        expected=archive_title(root,p,day)
        rec=records.get(p) if isinstance(records.get(p),dict) else {}
        errors=validate_record(p,rec,expected) if rec else ["decision_record_missing"]
        if not expected:errors.append("archive_title_missing")
        ok=not errors
        complete+=int(ok)
        out[p]={
            "status":"complete" if ok else "missing_or_invalid",
            "selected_title":rec.get("selected_title"),
            "candidates":rec.get("candidates",[]),
            "rationale":rec.get("rationale"),
            "basis":rec.get("basis",[]),
            "verified_views":rec.get("verified_views"),
            "errors":errors,
        }
    return {
        "date":day,
        "generated_at":datetime.now(TZ).isoformat(),
        "status":"complete" if complete==len(PROFILES) else "incomplete",
        "complete_count":complete,
        "expected_count":len(PROFILES),
        "profiles":out,
        "policy":"Headline decisions are editorial evidence; missing metrics stay null and are never inferred.",
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=ROOT)
    ap.add_argument("--date",default=datetime.now(TZ).date().isoformat())
    ap.add_argument("--output",type=Path)
    ap.add_argument("--strict",action="store_true")
    a=ap.parse_args()
    report=evaluate(a.root,a.date)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n","utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 1 if a.strict and report["status"]!="complete" else 0
if __name__=="__main__":
    raise SystemExit(main())
