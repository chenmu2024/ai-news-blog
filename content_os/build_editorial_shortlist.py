"""Convert already-collected public discovery into advisory editorial shortlist.
No external calls, no LLM, no publishing. Historical archive titles feed de-dup.
"""
from __future__ import annotations
import json, re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from editorial_intelligence import analyze, PROFILES

ROOT=Path(__file__).resolve().parents[1]
def archive_titles(profile,limit=30):
    folder=ROOT/profile/"archive"
    result=[]
    if folder.exists():
        for file in sorted(folder.glob("????-??-??.md"),reverse=True)[:limit]:
            text=file.read_text("utf-8")
            match=re.search(r"^# (.+)$",text,re.M)
            if match:result.append(match.group(1).strip())
    return result

def convert(discovery):
    result=[]
    for profile in PROFILES:
        record=discovery.get("profiles",{}).get(profile,{})
        for raw in record.get("articles",[]):
            if not raw.get("title") or not raw.get("url"):continue
            result.append({
                "profile":profile,"title":raw["title"],"url":raw["url"],
                "source":raw.get("platform") or "unknown",
                "published_at":raw.get("published_at"),
                "evidence_level":"unknown",
                "heat_verified":raw.get("heat_verified") is True,
                "relevance":60,"title_hook":50,
                "primary_text_verified":False,
            })
    return result

def main():
    today=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    latest=ROOT/"content_os/topic-intelligence/latest.json"
    if not latest.exists():raise SystemExit("No collected discovery archive available")
    data=json.loads(latest.read_text("utf-8"))
    if data.get("local_date")!=today:raise SystemExit("Stale discovery archive: cannot rank as today's research")
    history={profile:archive_titles(profile) for profile in PROFILES}
    ranking=analyze(convert(data),history)
    # Discovery/indexed headlines are NOT approved topics, even when numerically ranked.
    # Gate every event against trustworthy recency, heat and primary evidence before writing.
    for profile, events in ranking.items():
        for event in events:
            event["editorial_status"]="needs_manual_source_and_date_review"
            event["eligible_for_auto_selection"]=False
            if "unverified_heat" not in event["flags"]:
                event["flags"].append("original_publication_date_unverified")
            else:
                event["flags"].extend(["original_publication_date_unverified","insufficient_popularity_evidence"])
    report={"date":today,"status":"advisory_only","discovery_generated_at":data.get("generated_at"),
        "ranking_provenance":"public discovery, not verified WeChat virality",
        "profiles":ranking}
    out=ROOT/"content_os/editorial-intelligence"/f"{today}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n","utf-8")
    print("[EDITORIAL]",today, {p:len(v) for p,v in ranking.items()})
if __name__=="__main__":main()
