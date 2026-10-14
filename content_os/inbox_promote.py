"""Promote an individually verified article candidate, never call WeChat."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
try:
    from content_os.prearchive_validate import PROFILES, validate
    from content_os.title_decisions import validate_record
except ImportError:
    from prearchive_validate import PROFILES, validate
    from title_decisions import validate_record

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Shanghai")

def promote(root,profile,day,check_network=True, *, article_id=None):
    if profile not in PROFILES:raise ValueError("Unknown profile")
    if datetime.strptime(day,"%Y-%m-%d").date().isoformat()!=day:raise ValueError("Invalid day")
    if day!=datetime.now(TZ).date().isoformat():
        return {"profile":profile,"status":"SKIP","reasons":["not_today"]}
    from content_os.multi_draft import validate_article_id
    article_id=validate_article_id(day,article_id or day)
    source=root/"content_os"/"inbox"/profile/f"{article_id}.md"
    sidecar=root/"content_os"/"inbox"/profile/f"{article_id}.titles.json"
    archive=root/profile/"archive"/f"{article_id}.md"
    journal=root/profile/"status"/"draft-attempts"/f"{article_id}.json"
    if archive.exists() or journal.exists():
        return {"profile":profile,"status":"SKIP","reasons":["archive_or_attempt_exists"]}
    if not source.is_file() or not sidecar.is_file():
        return {"profile":profile,"status":"SKIP","reasons":["candidate_or_title_record_missing"]}
    try:
        record=json.loads(sidecar.read_text("utf-8"))
        if not isinstance(record,dict):raise ValueError("sidecar not an object")
    except (ValueError,OSError) as e:
        return {"profile":profile,"status":"FAIL","reasons":["invalid_title_sidecar",str(e)]}
    text=source.read_bytes().decode("utf-8")
    title=next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")),"")
    errors=validate_record(profile,record,title)
    evidence=record.get("evidence")
    if not isinstance(evidence,dict):evidence={}
    urls=evidence.get("source_urls")
    if not isinstance(urls,list) or not urls or any(not isinstance(x,str) or not x.startswith("https://") for x in urls):
        errors.append("real_https_source_evidence_required")
    if evidence.get("facts_checked") is not True:errors.append("facts_not_attested")
    if evidence.get("image_rights_checked") is not True:errors.append("image_rights_not_attested")
    if record.get("verified_views") is not None and not record.get("verified_views_source"):
        errors.append("views_must_be_null_unless_verified")
    if errors:return {"profile":profile,"status":"FAIL","reasons":errors}
    validated=validate(root,profile,day,source,skip_image_network=not check_network,article_id=article_id)
    if validated["status"]!="PASS" or not check_network:
        return {"profile":profile,"status":"FAIL","reasons":validated["errors"] or ["image_network_check_required"],
                "checks":validated.get("checks",[])}
    if archive.exists() or journal.exists():
        return {"profile":profile,"status":"SKIP","reasons":["archive_or_attempt_became_present"]}
    ledger=root/"content_os"/"title-decisions"/f"{article_id}.json"
    try:
        data=json.loads(ledger.read_text("utf-8")) if ledger.exists() else {}
        if not isinstance(data,dict) or not isinstance(data.get("profiles",{}),dict):raise ValueError()
    except (ValueError,OSError):
        return {"profile":profile,"status":"FAIL","reasons":["shared_ledger_invalid"]}
    records=data.setdefault("profiles",{})
    if profile in records and records[profile]!=record:
        return {"profile":profile,"status":"FAIL","reasons":["conflicting_title_decision"]}
    records[profile]=record
    data["date"]=day
    archive.parent.mkdir(parents=True,exist_ok=True)
    ledger.parent.mkdir(parents=True,exist_ok=True)
    archive.write_bytes(source.read_bytes())
    ledger.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"profile":profile,"status":"READY_FOR_COMMIT","archive":f"{profile}/archive/{article_id}.md",
            "sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),"title":title}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--profile",required=True,choices=PROFILES)
    p.add_argument("--date",default=datetime.now(TZ).date().isoformat())
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--article-id",help="YYYY-MM-DD--unique-slug, daily default unchanged")
    p.add_argument("--skip-image-network",action="store_true",help="Dry checks only; cannot promote")
    a=p.parse_args()
    result=promote(a.root.resolve(),a.profile,a.date,check_network=not a.skip_image_network,article_id=a.article_id)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["status"] in ("READY_FOR_COMMIT","SKIP") else 1
if __name__=="__main__":
    raise SystemExit(main())
