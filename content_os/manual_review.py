"""Validate append-only manual review decisions for Content OS.
This never approves anything automatically and never creates WeChat drafts.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

PROFILES={"qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion"}
STAGES={"source","topic","fact","image","draft","retry","metrics"}
DECISIONS={"approved","rejected","escalated","not_applicable"}

def load(path:Path):
    rows=[]
    if not path.exists(): return rows
    for n,line in enumerate(path.read_text("utf-8").splitlines(),1):
        if not line.strip(): continue
        x=json.loads(line)
        missing=[k for k in ("date","profile","stage","subject","decision","reviewer","evidence") if not x.get(k)]
        if missing: raise ValueError(f"line {n}: missing {missing}")
        if x["profile"] not in PROFILES: raise ValueError(f"line {n}: bad profile")
        if x["stage"] not in STAGES: raise ValueError(f"line {n}: bad stage")
        if x["decision"] not in DECISIONS: raise ValueError(f"line {n}: bad decision")
        if not isinstance(x["evidence"],list) or not x["evidence"]:
            raise ValueError(f"line {n}: evidence must be non-empty list")
        rows.append(x)
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,default=Path("content_os/manual-review/decisions.jsonl"))
    args=ap.parse_args()
    rows=load(args.input)
    print(json.dumps({"records":len(rows),"status":"valid"},ensure_ascii=False))
if __name__=="__main__": main()
