"""Validate Humanizer V4 reference-pollution evidence before archive.

The exact overlap scan runs upstream against the private 2,290-segment Library.
This public-repo gate validates that the scan covered the selected project-bank
references and passed the conservative 24-character exact-overlap threshold.
It never claims to be a copyright detector.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ACTIVATION="2026-10-14"
THRESHOLD=24

def check(root: Path, profile: str, day: str, article_id: str | None = None) -> dict:
    if day < ACTIVATION:
        return {"status":"NOT_REQUIRED","profile":profile,"date":day,"errors":[]}
    path=root/"content_os"/"editorial-reviews"/profile/((article_id or day)+".json")
    errors=[]
    try:
        rec=json.loads(path.read_text("utf-8"))
        human=rec.get("humanizer")
        if not isinstance(human,dict): raise ValueError("humanizer missing")
        refs=human.get("reference_examples")
        pollution=human.get("pollution_check")
        if not isinstance(refs,list) or not isinstance(pollution,dict):
            raise ValueError("pollution evidence missing")
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        return {"status":"FAIL","profile":profile,"date":day,
                "errors":["humanizer_pollution_record_missing_or_invalid"]}

    project_ids={str(x.get("reference_id")) for x in refs
                 if isinstance(x,dict) and x.get("origin")=="project_bank" and x.get("reference_id")}
    checked={str(x) for x in (pollution.get("reference_ids_checked") or [])}
    if pollution.get("engine")!="private_exact_overlap_v1":
        errors.append("humanizer_pollution_engine_mismatch")
    if pollution.get("status")!="PASS":
        errors.append("humanizer_reference_pollution_not_passed")
    if pollution.get("threshold_chars")!=THRESHOLD:
        errors.append("humanizer_pollution_threshold_mismatch")
    value=pollution.get("max_exact_overlap_chars")
    if not isinstance(value,int) or value<0 or value>=THRESHOLD:
        errors.append("humanizer_exact_overlap_too_high_or_invalid")
    if not project_ids or not project_ids.issubset(checked):
        errors.append("humanizer_pollution_did_not_check_all_project_references")
    web_refs=[x for x in refs if isinstance(x,dict) and x.get("origin")=="web_benchmark"]
    if web_refs and pollution.get("web_references_checked") is not True:
        errors.append("humanizer_web_reference_pollution_check_missing")
    return {"status":"FAIL" if errors else "PASS","profile":profile,"date":day,
            "errors":errors,"project_reference_count":len(project_ids),
            "max_exact_overlap_chars":value if isinstance(value,int) else None,
            "threshold_chars":THRESHOLD}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--profile",required=True)
    ap.add_argument("--date",required=True)
    ap.add_argument("--article-id")
    ap.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[2])
    args=ap.parse_args()
    result=check(args.root.resolve(),args.profile,args.date,article_id=args.article_id)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return int(result["status"]=="FAIL")
if __name__=="__main__":
    raise SystemExit(main())
