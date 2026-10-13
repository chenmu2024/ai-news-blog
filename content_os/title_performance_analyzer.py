"""Conservative title-performance analysis from verified article feedback only."""
from __future__ import annotations
import argparse,json
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT=Path(__file__).resolve().parents[1]
MIN_PROFILE=5
MIN_FEATURE=3

def analyze(db:dict)->dict:
    records=db.get("records") if isinstance(db,dict) else []
    if not isinstance(records,list): records=[]
    by_profile=defaultdict(list)
    for r in records:
        views=((r.get("metrics") or {}).get("views"))
        if type(views) is int:
            by_profile[r.get("profile")].append(r)
    profiles={}
    for profile,rows in sorted(by_profile.items()):
        baseline=mean([r["metrics"]["views"] for r in rows]) if rows else None
        feats=defaultdict(list)
        for r in rows:
            for f in r.get("headline_features") or []:
                feats[f].append(r["metrics"]["views"])
        result=[]
        for feat,vals in sorted(feats.items()):
            avg=mean(vals)
            lift=(avg/baseline) if baseline not in (None,0) else None
            result.append({
                "feature":feat,"count":len(vals),"avg_views":round(avg,2),
                "lift_vs_profile_avg":round(lift,3) if lift is not None else None,
                "usable_for_learning":len(rows)>=MIN_PROFILE and len(vals)>=MIN_FEATURE,
            })
        usable=[x for x in result if x["usable_for_learning"]]
        profiles[profile]={
            "verified_view_records":len(rows),
            "baseline_avg_views":round(baseline,2) if baseline is not None else None,
            "status":"learnable" if len(rows)>=MIN_PROFILE else "insufficient_data",
            "features":result,
            "observations":[
                {"feature":x["feature"],"direction":"positive" if x["lift_vs_profile_avg"]>=1.15 else "negative",
                 "count":x["count"],"lift_vs_profile_avg":x["lift_vs_profile_avg"],
                 "warning":"Association only; not causal."}
                for x in usable if x["lift_vs_profile_avg"] is not None and (x["lift_vs_profile_avg"]>=1.15 or x["lift_vs_profile_avg"]<=0.85)
            ],
        }
    return {
        "schema_version":1,"profiles":profiles,
        "minimums":{"profile_verified_views":MIN_PROFILE,"feature_samples":MIN_FEATURE},
        "policy":"Only verified integer views are analyzed. Associations are advisory, never causal claims or automatic title rules."
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,default=ROOT/"content_os/feedback-learning/article_feedback_latest.json")
    ap.add_argument("--output",type=Path,default=ROOT/"content_os/feedback-learning/title_performance_latest.json")
    a=ap.parse_args()
    try:db=json.loads(a.input.read_text("utf-8"))
    except (OSError,ValueError):db={"records":[]}
    report=analyze(db)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n","utf-8")
    print(json.dumps({p:x["status"] for p,x in report["profiles"].items()},ensure_ascii=False))
if __name__=="__main__":main()
