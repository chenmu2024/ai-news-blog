"""Hard-risk Humanizer V3 check for new candidate articles.

This is not an AI authorship detector. It catches only obvious template/structure
risks after the model-agnostic Humanizer editing pass. Facts are checked elsewhere.
"""
from __future__ import annotations
import argparse
import json
import math
import re
from pathlib import Path

PROFILES={"qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion"}
ACTIVATION="2026-10-14"
TEMPLATES=[
    r"首先[,，]?", r"其次[,，]?", r"最后[,，]?", r"综上所述", r"总而言之",
    r"值得注意的是", r"与此同时", r"总体来看", r"从某种程度上(?:说|看)",
    r"由此可见", r"不难发现", r"可以看出", r"在当今.{0,16}(?:时代|背景下)",
]
PROFILE_EXTRA={
    "jingyun":[r"女人到了\d+岁",r"每个女人都应该",r"你值得被爱",r"一定要学会爱自己"],
    "wechat":[r"AI正在(?:重塑|改变|颠覆).{0,20}(?:世界|行业|未来)",r"未来已来"],
    "business":[r"人人都能领",r"错过就亏",r"赶紧收藏"],
    "parenting":[r"家长一定要知道",r"不领就亏",r"错过再等一年"],
}
CONTRAST=re.compile(r"不是[^。！？\n]{0,42}而是")
NUMBERED_HEADING=re.compile(r"(?m)^#{2,4}\s*(?:[一二三四五六七八九十]+|\d+)[、.．：:]")
IMAGE=re.compile(r"!\[[^\]]*\]\([^)]+\)")
COMMENT=re.compile(r"<!--.*?-->",re.S)

def visible(md):
    text=COMMENT.sub("",md)
    text=IMAGE.sub("",text)
    text=re.sub(r"(?m)^#{1,6}\s*","",text)
    return text.strip()

def _cv(values):
    if len(values)<2:return 1.0
    mean=sum(values)/len(values)
    if not mean:return 1.0
    var=sum((x-mean)**2 for x in values)/len(values)
    return math.sqrt(var)/mean

def evaluate(profile,markdown):
    if profile not in PROFILES: raise ValueError("unknown profile")
    body=visible(markdown)
    paras=[re.sub(r"\s+","",p) for p in re.split(r"\n\s*\n",body) if len(re.sub(r"\s+","",p))>=12]
    sents=[re.sub(r"\s+","",s) for s in re.split(r"(?<=[。！？!?])",body) if len(re.sub(r"\s+","",s))>=8]
    template_hits=sum(len(re.findall(p,body,re.I)) for p in TEMPLATES)
    extra_hits=sum(len(re.findall(p,body,re.I)) for p in PROFILE_EXTRA.get(profile,[]))
    contrast_hits=len(CONTRAST.findall(body))
    headings=len(NUMBERED_HEADING.findall(markdown))
    para_cv=_cv([len(p) for p in paras])
    sent_cv=_cv([len(s) for s in sents])
    risks=[]
    if template_hits>=4: risks.append("template_connectors_dense")
    if extra_hits>=2: risks.append("profile_specific_cliche_dense")
    if contrast_hits>=3: risks.append("repeated_not_x_but_y")
    if headings>=5 and len(paras)>=7: risks.append("ppt_like_numbered_structure")
    if len(paras)>=7 and para_cv<0.24: risks.append("paragraphs_too_uniform")
    if len(sents)>=12 and sent_cv<0.32: risks.append("sentences_too_uniform")
    score=template_hits+extra_hits*2+contrast_hits*2+(3 if headings>=5 else 0)+(3 if "paragraphs_too_uniform" in risks else 0)
    return {"status":"FAIL" if risks else "PASS","profile":profile,"risk_score":score,
            "template_hits":template_hits,"profile_cliche_hits":extra_hits,
            "contrast_hits":contrast_hits,"numbered_headings":headings,
            "paragraph_cv":round(para_cv,3),"sentence_cv":round(sent_cv,3),
            "risks":risks,
            "note":"Hard-risk style check only; not an AI authorship detector."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--profile",required=True,choices=sorted(PROFILES))
    ap.add_argument("--article",required=True,type=Path)
    ap.add_argument("--date")
    args=ap.parse_args()
    if args.date and args.date < ACTIVATION:
        print(json.dumps({"status":"NOT_REQUIRED","profile":args.profile,"date":args.date},ensure_ascii=False,indent=2))
        return 0
    result=evaluate(args.profile,args.article.read_text("utf-8"))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return int(result["status"]=="FAIL")
if __name__=="__main__":
    raise SystemExit(main())
