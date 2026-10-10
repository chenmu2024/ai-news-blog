"""Convert already-collected public discovery into advisory editorial shortlist.
No external calls, no LLM, no publishing. Historical archive titles feed de-dup.
"""
from __future__ import annotations
import json, re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
try:
    from content_os.editorial_intelligence import analyze, PROFILES
except ImportError:
    from editorial_intelligence import analyze, PROFILES

PROFILE_POSITIVE = {
    "qiezhi": re.compile(r"毛选|毛泽东|调查研究|实践论|矛盾论|群众路线|实事求是"),
    "wechat": re.compile(r"AI|Agent|SaaS|创业|独立开发|公司|产品|融资|收入|工作流", re.I),
    "business": re.compile(r"公司|品牌|营收|利润|业绩|门店|收购|融资|上市|转型|增长|亏损|供应链"),
    "zizhitongjian": re.compile(r"资治通鉴|司马光|智伯|赵魏韩|秦|汉|魏|晋|唐|宋|君臣|决策|权力"),
    "parenting": re.compile(r"家长|孩子|学校|老师|教育|家校|青春期|手机|学习|作业|同伴|家庭"),
    "jingyun": re.compile(r"女性|女人|中年|婚姻|职场|家庭|母女|经济独立|养老|工作"),
    "fashion": re.compile(r"杨幂|刘亦菲|赵露思|Jisoo|Jennie|张员瑛|宋慧乔|林允儿|机场|时装周|穿搭|造型|礼服|秀场", re.I),
}
MARKETING = re.compile(r"福利|课程|合集|PDF下载|加微信|领取|训练营|知识付费|好书推荐|全套")
SENSATIONAL = re.compile(r"炸锅|低胸|身材大变|走光|跳楼|自杀|惨死|杀害|万箭穿心")
RELATIONSHIP_CLICKBAIT = re.compile(r"实录[:：]?|婚外情|出轨|抓奸|原配|小三")
FASHION_CONTEXT = re.compile(r"穿搭|造型|礼服|秀场|街拍|西装|裙|外套|鞋|包|上衣|裤|风衣|针织|大衣")
CELEBRITY = re.compile(r"杨幂|刘亦菲|赵露思|Jisoo|Jennie|张员瑛|宋慧乔|林允儿", re.I)

def editorial_quality(profile, title):
    flags=[]
    relevance=60
    hook=50
    if not PROFILE_POSITIVE[profile].search(title):
        flags.append("weak_profile_match")
        relevance-=25
    else:
        relevance+=15
    if MARKETING.search(title):
        flags.append("marketing_or_sales_content")
        relevance-=35
    if SENSATIONAL.search(title):
        flags.append("sensational_or_sensitive_framing")
        relevance-=25
        hook-=10
    if profile=="jingyun" and RELATIONSHIP_CLICKBAIT.search(title):
        flags.append("relationship_clickbait_requires_manual_review")
        relevance-=25
    if profile=="fashion":
        if not CELEBRITY.search(title):
            flags.append("fashion_no_named_priority_celebrity")
            relevance-=25
        if not FASHION_CONTEXT.search(title):
            flags.append("fashion_weak_outfit_context")
            relevance-=25
    if profile=="business" and not re.search(r"公司|品牌|营收|利润|业绩|门店|收购|融资|上市|供应链", title):
        flags.append("business_weak_company_event_signal")
        relevance-=20
    if profile=="zizhitongjian" and MARKETING.search(title):
        flags.append("history_commercial_content")
    return max(0,min(100,relevance)), max(0,min(100,hook)), flags

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
            relevance, hook, editorial_flags = editorial_quality(profile, raw["title"])
            result.append({
                "profile":profile,"title":raw["title"],"url":raw["url"],
                "source":raw.get("platform") or "unknown",
                "published_at":raw.get("published_at"),
                "evidence_level":"unknown",
                "heat_verified":raw.get("heat_verified") is True,
                "relevance":relevance,"title_hook":hook,
                "editorial_flags":editorial_flags,
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
            combined=list(dict.fromkeys(event.get("flags",[])+event.get("editorial_flags",[])))
            event["flags"]=combined
            severe={"marketing_or_sales_content","fashion_no_named_priority_celebrity","fashion_weak_outfit_context",
                    "business_weak_company_event_signal","sensational_or_sensitive_framing","relationship_clickbait_requires_manual_review","weak_profile_match"}
            event["editorial_status"]="reject_or_research_only" if severe.intersection(combined) else "needs_manual_source_and_date_review"
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
