"""Build seven advisory account-learning profiles without fabricating causality."""
from __future__ import annotations
import argparse,json
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT=Path(__file__).resolve().parents[1]
PROFILES=("qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion")
MIN_VIEWS=5
MIN_ROLE=3

def build(db:dict,title_report:dict)->dict:
    records=db.get("records") if isinstance(db,dict) else []
    by=defaultdict(list)
    for r in records if isinstance(records,list) else []:
        by[r.get("profile")].append(r)
    out={}
    for profile in PROFILES:
        rows=by.get(profile,[])
        numeric=[r for r in rows if type(((r.get("metrics") or {}).get("views"))) is int]
        role_views=defaultdict(list)
        for r in numeric:
            for role in r.get("humanizer_roles") or []:
                role_views[role].append(r["metrics"]["views"])
        role_assoc=[]
        baseline=mean([r["metrics"]["views"] for r in numeric]) if numeric else None
        for role,vals in sorted(role_views.items()):
            avg=mean(vals)
            role_assoc.append({
                "role":role,"count":len(vals),"avg_views":round(avg,2),
                "lift_vs_profile_avg":round(avg/baseline,3) if baseline else None,
                "usable_for_learning":len(numeric)>=MIN_VIEWS and len(vals)>=MIN_ROLE,
                "warning":"Association only; Humanizer roles usually co-occur and are not isolated causal treatments."
            })
        tr=(title_report.get("profiles") or {}).get(profile,{})
        title_obs=tr.get("observations") if isinstance(tr.get("observations"),list) else []
        if len(numeric)<MIN_VIEWS:
            next_experiment={
                "type":"collect_feedback",
                "instruction":"继续记录真实阅读量；达到至少5篇可核验数据前，不根据表现自动改变标题或文风。",
                "reason":f"当前只有{len(numeric)}篇可核验阅读数据。"
            }
            evidence_level="insufficient"
        else:
            pos=next((x for x in title_obs if x.get("direction")=="positive"),None)
            if pos:
                next_experiment={
                    "type":"single_variable_title_test",
                    "instruction":f"下一周只测试标题特征 {pos['feature']}，其余选题与正文质量标准保持不变。",
                    "reason":f"该特征现有{pos['count']}篇样本，关联lift={pos['lift_vs_profile_avg']}；仅作相关性实验。"
                }
            else:
                next_experiment={
                    "type":"hold_baseline",
                    "instruction":"保持当前标题与Humanizer规则，继续积累样本，不为了少量波动改方向。",
                    "reason":"尚无达到最低样本并表现出明确关联的标题特征。"
                }
            evidence_level="early"
        out[profile]={
            "article_records":len(rows),
            "verified_view_records":len(numeric),
            "evidence_level":evidence_level,
            "title_observations":title_obs,
            "humanizer_role_associations":role_assoc,
            "next_experiment":next_experiment,
            "auto_apply":False,
        }
    return {
        "schema_version":1,"profiles":out,
        "policy":"Learning profiles are advisory. No finding may override fact, source, copyright, Humanizer pollution or user-approval gates. No automatic strategy change from fewer than 5 verified view records."
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--db",type=Path,default=ROOT/"content_os/feedback-learning/article_feedback_latest.json")
    ap.add_argument("--titles",type=Path,default=ROOT/"content_os/feedback-learning/title_performance_latest.json")
    ap.add_argument("--output",type=Path,default=ROOT/"content_os/feedback-learning/account_learning_latest.json")
    a=ap.parse_args()
    def read(p):
        try:return json.loads(p.read_text("utf-8"))
        except (OSError,ValueError):return {}
    report=build(read(a.db),read(a.titles))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n","utf-8")
    print(json.dumps({p:x["evidence_level"] for p,x in report["profiles"].items()},ensure_ascii=False))
if __name__=="__main__":main()
