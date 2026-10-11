"""Dispatch an existing WeChat DRAFT workflow only for verified, NEW bot-promoted archives.

GitHub's GITHUB_TOKEN commits do not fire downstream push workflows. This
component calls only GitHub's workflow_dispatch; it NEVER calls WeChat.
Ambiguous/previous runs fail closed.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Shanghai")
PROFILES=("qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion")

def classify(root:Path, profile:str, day:str, commit_title:str,
             runs:list, status:dict) -> tuple[bool,str]:
    expected=f"content({profile}): promote verified {day} archive"
    if commit_title!=expected:return False,"not_verified_promotion_commit"
    if not (root/profile/"archive"/f"{day}.md").is_file():return False,"archive_missing"
    if (root/profile/"status"/"draft-attempts"/f"{day}.json").exists():
        return False,"attempt_journal_present"
    if status.get("article_path")==f"{profile}/archive/{day}.md":
        return False,"same_day_status_receipt"
    # Need a complete recent run page to prove there was no earlier attempt.
    if not isinstance(runs,list) or len(runs)>=100:return False,"run_history_incomplete"
    for run in runs:
        if run.get("status") in ("queued","in_progress","waiting","pending","requested"):
            return False,"draft_workflow_in_progress"
        try:
            created=datetime.fromisoformat(str(run["created_at"]).replace("Z","+00:00"))
            if created.astimezone(TZ).date().isoformat()==day:
                return False,"same_day_workflow_run_exists"
        except (ValueError,TypeError,KeyError):
            return False,"unparseable_workflow_run"
    return True,"bot_archive_no_prior_attempt"

def classify_verified_predraft_failure(root: Path, profile: str, day: str,
                                      commit_title: str, runs: list, status: dict,
                                      jobs: list) -> tuple[bool, str]:
    """One proven before-API failure may be retried once; never inferred.

    This narrowly repairs the 2026-10-11 Zizhitongjian missing 'requests'
    source-gate dependency. The inspected workflow step failed before any
    publisher/media API step was reached. No other failure is auto-retried.
    """
    if profile != "zizhitongjian" or day != "2026-10-11":
        return False, "not_in_verified_recovery_scope"
    # Reuse immutable-archive, exact git commit, receipt and journal guards.
    if commit_title != f"content({profile}): promote verified {day} archive":
        return False, "not_verified_promotion_commit"
    if not (root/profile/"archive"/f"{day}.md").is_file():
        return False, "archive_missing"
    if (root/profile/"status"/"draft-attempts"/f"{day}.json").exists():
        return False, "attempt_journal_present"
    if status.get("article_path") == f"{profile}/archive/{day}.md":
        return False, "same_day_status_receipt"
    if not isinstance(runs,list) or len(runs) >= 100 or not isinstance(jobs,list):
        return False, "incomplete_recovery_evidence"
    same = []
    for run in runs:
        if run.get("status") in ("queued","in_progress","waiting","pending","requested"):
            return False, "another_run_in_progress"
        try:
            dt=datetime.fromisoformat(str(run["created_at"]).replace("Z","+00:00"))
        except (ValueError,TypeError,KeyError):
            return False, "unparseable_run_created"
        if dt.astimezone(TZ).date().isoformat() == day:
            same.append(run)
    if len(same) != 1:
        return False, "recovery_one_previous_run_only"
    previous=same[0]
    if not (previous.get("status") == "completed"
            and previous.get("conclusion") == "failure"
            and previous.get("event") == "workflow_dispatch"):
        return False, "previous_run_not_proven_predraft_failure"
    if len(jobs) != 1 or jobs[0].get("conclusion") != "failure":
        return False, "previous_job_not_proven"
    steps=jobs[0].get("steps")
    if not isinstance(steps,list):
        return False,"missing_previous_job_steps"
    by_name={s.get("name"):s.get("conclusion") for s in steps if isinstance(s,dict)}
    # Strictly require failure at first source Gate, and the draft step skipped.
    if (by_name.get("Original-text source gate") != "failure"
        or by_name.get("Create Zizhi Tongjian WeChat draft only") != "skipped"
        or by_name.get("Draft idempotency preflight") != "success"):
        return False,"wechat_draft_boundary_not_proven_unreached"
    return True,"verified_one_time_predraft_source_gate_recovery"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--profile",required=True,choices=PROFILES)
    p.add_argument("--date",default=datetime.now(TZ).date().isoformat())
    p.add_argument("--root",type=Path,default=ROOT)
    a=p.parse_args()
    if a.date!=datetime.now(TZ).date().isoformat():
        print("[SAFE_DISPATCH] not today's archive");return 0
    token=os.getenv("GH_TOKEN","")
    repo=os.getenv("GITHUB_REPOSITORY","")
    if not token or "/" not in repo:
        print("::error::Missing GitHub token/repository; cannot check workflow history");return 1
    archive=f"{a.profile}/archive/{a.date}.md"
    root=a.root.resolve()
    title=subprocess.run(["git","log","-1","--format=%s","--",archive],
                         cwd=root,text=True,capture_output=True,check=True).stdout.strip()
    status_path=root/a.profile/"status"/"latest.json"
    try:status=json.loads(status_path.read_text("utf-8"))
    except (OSError,ValueError):status={}
    api=f"https://api.github.com/repos/{repo}/actions/workflows/{a.profile}-draft.yml"
    headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
             "X-GitHub-Api-Version":"2022-11-28"}
    try:
        req=Request(api+"/runs?per_page=100",headers=headers)
        with urlopen(req,timeout=25) as r:
            runs=json.load(r).get("workflow_runs")
        allow,why=classify(root,a.profile,a.date,title,runs,status)
        if not allow and why == "same_day_workflow_run_exists" and a.profile == "zizhitongjian":
            previous=[r for r in runs if
                      datetime.fromisoformat(str(r.get("created_at","1970-01-01T00:00:00Z")).replace("Z","+00:00")).astimezone(TZ).date().isoformat() == a.date]
            if len(previous) == 1 and isinstance(previous[0].get("id"),int):
                req=Request(f"https://api.github.com/repos/{repo}/actions/runs/{previous[0]['id']}/jobs?per_page=100",headers=headers)
                with urlopen(req,timeout=25) as response:
                    job_payload=json.load(response)
                if job_payload.get("total_count") == 1:
                    allow,why=classify_verified_predraft_failure(
                        root,a.profile,a.date,title,runs,status,job_payload.get("jobs"))
        if not allow:
            print("[SAFE_DISPATCH]",a.profile,"SKIP",why)
            return 0
        body=json.dumps({"ref":"main"}).encode("utf-8")
        req=Request(api+"/dispatches",data=body,headers={**headers,"Content-Type":"application/json"},method="POST")
        with urlopen(req,timeout=25) as r:
            if r.status!=204:raise RuntimeError("Unexpected workflow_dispatch status")
        print("[SAFE_DISPATCH]",a.profile,"DISPATCHED",archive)
        return 0
    except Exception as exc:
        # Never retry an ambiguous workflow_dispatch response without fetching
        # new workflow history and checking for same-day run.
        print("::error::",a.profile,"unable to prove or send first safe draft workflow:",str(exc))
        return 1

if __name__=="__main__":
    raise SystemExit(main())
