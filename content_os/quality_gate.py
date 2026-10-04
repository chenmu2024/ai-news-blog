from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

PROFILES = {
    "ai_business": {
        "name": "陈慕｜AI 一人公司实战",
        "max_score": 30,
        "warn_score": 40,
        "min_body_chars": 1800,
        "max_body_chars": 5200,
        "min_fact_signals": 4,
        "min_stance_signals": 2,
    },
    "business_story": {
        "name": "生意显微镜｜商业故事",
        "max_score": 30,
        "warn_score": 40,
        "min_body_chars": 1800,
        "max_body_chars": 5600,
        "min_fact_signals": 5,
        "min_stance_signals": 1,
    },
    "zizhitongjian": {
        "name": "资治通鉴｜原典·人性·决策",
        "max_score": 30,
        "warn_score": 40,
        "min_body_chars": 1500,
        "max_body_chars": 5000,
        "min_fact_signals": 4,
        "min_stance_signals": 1,
    },
    "parenting": {
        "name": "陈慕｜育儿与家庭教育",
        "max_score": 30,
        "warn_score": 40,
        "min_body_chars": 1500,
        "max_body_chars": 5000,
        "min_fact_signals": 3,
        "min_stance_signals": 1,
    },
    "qiezhi": {
        "name": "且知｜毛选/思想方法",
        "max_score": 30,
        "warn_score": 40,
        "min_body_chars": 1400,
        "max_body_chars": 4800,
        "min_fact_signals": 2,
        "min_stance_signals": 1,
    },
}

TEMPLATE_PATTERNS = [
    r"首先[,，]?", r"其次[,，]?", r"最后[,，]?", r"综上所述",
    r"值得注意的是", r"需要注意的是", r"随着.{0,16}(?:发展|普及|演进)",
    r"在当今.{0,18}(?:时代|背景下)", r"不可否认", r"毋庸置疑",
    r"总的来说", r"由此可见",
]

INTERNAL_PATTERNS = [
    # Only flag editor/production metadata in an editorial context.
    # Do not flag ordinary article discussion of Prompt/HTML/Markdown/HTTP.
    r"(?m)^#{1,6}\\s*(?:数据核验说明|来源核验说明|配图建议|图片说明|发布说明|编辑说明|内部备注|生成说明)\\s*$",
    r"(?m)^>\\s*配图建议[：:].*$",
    r"(?:内部|系统|编辑|制作)\\s*Prompt\\s*[：:]",
    r"(?:Markdown|HTML|HTTP|Content-Type)\\s*(?:说明|格式说明|技术说明|状态码说明)",
    r"WECHAT_CARD", r"QIEZHI_CARD",
]

STANCE_PATTERNS_AI = [
    r"我(?:更|最)?(?:看重|认为|觉得|判断|会|建议|倾向|不建议|更愿意|真正关心)",
    r"如果是我", r"我会先", r"我反而", r"我的判断",
]
STANCE_PATTERNS_BUSINESS = [
    r"我(?:更|最)?(?:看重|认为|判断|关心|倾向|不认为)",
    r"我的判断", r"关键不在", r"真正的问题", r"更值得看的是",
    r"真正决定", r"这家公司真正", r"代价是", r"护城河",
]
STANCE_PATTERNS_TONGJIAN = [
    r"我的判断", r"真正的问题", r"更值得看的是", r"放回当时",
    r"从这个选择看", r"这里真正", r"他当时", r"并不是因为",
]
STANCE_PATTERNS_PARENTING = [
    r"真正的问题", r"更重要的是", r"父母可以", r"可以先",
    r"不妨先", r"与其", r"孩子需要", r"这里不是",
]
STANCE_PATTERNS_QIEZHI = [
    r"今天(?:我们|你|普通人|做事)", r"真正要做的", r"更重要的是",
    r"落到今天", r"具体到", r"可以先", r"不妨先",
]

FACT_PATTERNS_AI = [
    r"\d+(?:\.\d+)?%", r"\d+(?:\.\d+)?\s*(?:万|亿|美元|元|人|个月|年|天|次|家|个|倍|GB|MB|TB|B|M|K)",
    r"(?:20\d{2}|19\d{2})[年/-]", r"\b(?:ARR|MRR|CPC|KD|GPU|API|SEO|SaaS)\b",
]
FACT_PATTERNS_BUSINESS = [
    r"\d+(?:\.\d+)?%", r"\d+(?:\.\d+)?\s*(?:万|亿|美元|元|人|家|店|门店|年|月|天|倍)",
    r"(?:20\d{2}|19\d{2})[年/-]", r"\b(?:GMV|ARR|IPO|CAGR|SKU|毛利率|净利率)\b",
    r"(?:营收|收入|利润|亏损|销量|门店|融资|估值|市值|市场份额|客单价|毛利)",
]
FACT_PATTERNS_TONGJIAN = [
    r"《资治通鉴》", r"司马光", r"臣光曰", r"卷[一二三四五六七八九十百零〇0-9]{1,8}",
    r"(?:周|秦|汉|魏|晋|宋|齐|梁|陈|隋|唐|后梁|后唐|后晋|后汉|后周)纪",
    r"(?:前)?\d{1,4}年", r"(?:皇帝|太子|丞相|将军|刺史|太守|尚书|司徒|司马)",
]
FACT_PATTERNS_PARENTING = [
    r"\d+\s*(?:岁|个月|分钟|小时|天|周|年|次)",
    r"(?:儿童|青少年|青春期|学龄前|学龄期|睡眠|情绪|依恋|同伴|学习|家庭|父母)",
    r"(?:WHO|UNICEF|AAP|CDC|卫健|儿科学会|心理学会)",
]
FACT_PATTERNS_QIEZHI = [
    r"《[^》]{2,30}》", r"毛泽东",
    r"《实践论》|《矛盾论》|《论持久战》|《反对本本主义》",
    r"\d+\s*(?:步|类|条|次|个|点)",
]

def strip_production_markup(md: str) -> str:
    text = re.sub(r"<!--\s*ZZTJ_SOURCE\s*\{[\s\S]*?\}\s*-->", "", md, flags=re.S)
    text = re.sub(r"<!--\s*(?:WECHAT_CARD|QIEZHI_CARD)\s+.*?-->", "", text, flags=re.S)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = re.sub(r"\*\*|__|~~|`", "", text)
    return text.strip()

def paragraphs(text: str) -> list[str]:
    return [re.sub(r"\s+", "", p) for p in re.split(r"\n\s*\n", text) if re.sub(r"\s+", "", p)]

def sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?；;]\s*", text)
    return [re.sub(r"\s+", "", s) for s in parts if len(re.sub(r"\s+", "", s)) >= 6]

def count_matches(patterns: list[str], text: str) -> int:
    return sum(len(re.findall(p, text, flags=re.I)) for p in patterns)

def regularity_penalty(paras: list[str]) -> tuple[int, dict]:
    lens = [len(p) for p in paras if len(p) >= 20]
    if len(lens) < 5:
        return 0, {"paragraphs": len(lens), "cv": None}
    mean = statistics.mean(lens)
    stdev = statistics.pstdev(lens)
    cv = stdev / mean if mean else 0
    if cv < 0.18:
        return 15, {"paragraphs": len(lens), "cv": round(cv, 3)}
    if cv < 0.28:
        return 8, {"paragraphs": len(lens), "cv": round(cv, 3)}
    return 0, {"paragraphs": len(lens), "cv": round(cv, 3)}

def sentence_repeat_penalty(sents: list[str]) -> tuple[int, dict]:
    if len(sents) < 8:
        return 0, {"sentences": len(sents), "repeated_starts": 0}
    starts = [s[:4] for s in sents if len(s) >= 8]
    freq = {}
    for x in starts:
        freq[x] = freq.get(x, 0) + 1
    repeated = sum(v - 1 for v in freq.values() if v >= 2)
    ratio = repeated / max(1, len(starts))
    if ratio >= 0.22:
        return 15, {"sentences": len(sents), "repeated_starts": repeated, "ratio": round(ratio, 3)}
    if ratio >= 0.12:
        return 8, {"sentences": len(sents), "repeated_starts": repeated, "ratio": round(ratio, 3)}
    return 0, {"sentences": len(sents), "repeated_starts": repeated, "ratio": round(ratio, 3)}

def evaluate(md: str, profile_key: str) -> dict:
    profile = PROFILES[profile_key]
    body = strip_production_markup(md)
    ps = paragraphs(body)
    ss = sentences(body)

    internal_hits = count_matches(INTERNAL_PATTERNS, body)
    template_hits = count_matches(TEMPLATE_PATTERNS, body)
    if profile_key == "qiezhi":
        fact_patterns = FACT_PATTERNS_QIEZHI
        stance_patterns = STANCE_PATTERNS_QIEZHI
    elif profile_key == "parenting":
        fact_patterns = FACT_PATTERNS_PARENTING
        stance_patterns = STANCE_PATTERNS_PARENTING
    elif profile_key == "zizhitongjian":
        fact_patterns = FACT_PATTERNS_TONGJIAN
        stance_patterns = STANCE_PATTERNS_TONGJIAN
    elif profile_key == "business_story":
        fact_patterns = FACT_PATTERNS_BUSINESS
        stance_patterns = STANCE_PATTERNS_BUSINESS
    else:
        fact_patterns = FACT_PATTERNS_AI
        stance_patterns = STANCE_PATTERNS_AI
    fact_hits = count_matches(fact_patterns, body)
    stance_hits = count_matches(stance_patterns, body)

    score = 0
    score += min(20, template_hits * 4)

    sent_penalty, sent_meta = sentence_repeat_penalty(ss)
    score += sent_penalty

    para_penalty, para_meta = regularity_penalty(ps)
    score += para_penalty

    if fact_hits < profile["min_fact_signals"]:
        score += 20
    elif fact_hits < profile["min_fact_signals"] * 2:
        score += 8

    if stance_hits < profile["min_stance_signals"]:
        score += 15
    elif stance_hits < profile["min_stance_signals"] * 2:
        score += 6

    very_short = sum(1 for p in ps if 2 <= len(p) <= 18)
    short_ratio = very_short / max(1, len(ps))
    if len(ps) >= 8 and short_ratio > 0.55:
        score += 10
    elif len(ps) >= 8 and short_ratio > 0.35:
        score += 5

    hard_failures = []
    if internal_hits:
        hard_failures.append(f"检测到 {internal_hits} 处内部生产/编辑元信息")
    body_chars = len(re.sub(r"\s+", "", body))
    if body_chars < profile["min_body_chars"]:
        hard_failures.append(f"正文过短：{body_chars} 字符 < {profile['min_body_chars']}")
    if body_chars > profile["max_body_chars"]:
        hard_failures.append(f"正文过长：{body_chars} 字符 > {profile['max_body_chars']}")

    status = "PASS"
    if hard_failures or score > profile["warn_score"]:
        status = "FAIL"
    elif score > profile["max_score"]:
        status = "WARN"

    return {
        "status": status,
        "profile": profile_key,
        "profile_name": profile["name"],
        "score": score,
        "body_chars": body_chars,
        "template_hits": template_hits,
        "internal_hits": internal_hits,
        "fact_signals": fact_hits,
        "stance_signals": stance_hits,
        "paragraph_regularity": para_meta,
        "sentence_repetition": sent_meta,
        "very_short_paragraph_ratio": round(short_ratio, 3),
        "hard_failures": hard_failures,
        "note": "这是文风/可读性启发式 Gate，不是作者身份或 AI 生成检测器。",
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True)
    ap.add_argument("--profile", required=True, choices=sorted(PROFILES))
    ap.add_argument("--json-out")
    ap.add_argument("--allow-warn", action="store_true")
    args = ap.parse_args()

    article = Path(args.article)
    if not article.exists():
        print(f"[QUALITY_GATE] FAIL: article not found: {article}", file=sys.stderr)
        return 2

    result = evaluate(article.read_text(encoding="utf-8"), args.profile)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")

    if result["status"] == "FAIL":
        return 1
    if result["status"] == "WARN" and not args.allow_warn:
        return 3
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
