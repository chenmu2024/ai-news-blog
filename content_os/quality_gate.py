from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

from editorial_guard import assess_editorial_title

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
        # Internal legacy profile key retained for backwards-compatible workflows.
        "name": "民生政策与福利指南｜办事攻略",
        "max_score": 30,
        "warn_score": 40,
        "min_body_chars": 850,
        "max_body_chars": 4600,
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
    "fashion": {
        "name": "女装穿搭｜Image-first",
        "max_score": 30,
        "warn_score": 40,
        "min_body_chars": 1100,
        "max_body_chars": 3800,
        "min_fact_signals": 3,
        "min_stance_signals": 2,
    },
    "jingyun": {
        "name": "静筠日记｜女性生活",
        "max_score": 30,
        "warn_score": 40,
        "min_body_chars": 1500,
        "max_body_chars": 5000,
        "min_fact_signals": 2,
        "min_stance_signals": 2,
    },
    "parenting": {
        "name": "民生家庭政策与生育福利指南",
        "max_score": 30,
        "warn_score": 40,
         # Family welfare explainer: actionable, sourced prose with verified cards.
        "min_body_chars": 850,
        "max_body_chars": 4600,
        "min_fact_signals": 5,
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
    # Public-benefit explainers prioritize accurate eligibility/action over opinions.
    r"符合条件", r"不符合", r"先确认", r"需要注意", r"具体以",
    r"要分清", r"可以申请", r"办理前", r"不要混淆",
]
STANCE_PATTERNS_TONGJIAN = [
    r"我的判断", r"真正的问题", r"更值得看的是", r"放回当时",
    r"从这个选择看", r"这里真正", r"他当时", r"并不是因为",
]
STANCE_PATTERNS_FASHION = [
    r"真正好看", r"最值得抄", r"关键在", r"普通人", r"不建议",
    r"更适合", r"最容易错", r"预算", r"版型", r"比例",
]
STANCE_PATTERNS_JINGYUN = [
    r"我更愿意", r"真正难的是", r"更诚实的说法", r"现实是",
    r"问题不在", r"并不意味着", r"未必", r"代价是",
    r"很多女人", r"到了这个年纪", r"真正需要", r"更重要的是",
]
STANCE_PATTERNS_PARENTING = [
    r"符合条件", r"不符合", r"先确认", r"申请前", r"需要注意",
    r"具体以", r"可以申领", r"不要混淆", r"家长可以",
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
    r"\d+(?:\.\d+)?%", r"\d+(?:\.\d+)?\s*(?:万|亿|元|个月|年|月|天|周)",
    r"(?:20\d{2}|19\d{2})[年/-]",
    r"(?:社保|医保|人社|公积金|养老金|生育津贴|失业金|工伤|职工医保|居民医保|产假|育儿补贴)",
    r"(?:申请|申领|缴费|到账|受理|审核|待遇|材料|期限|工作日|身份证|居住证|户籍|参保)",
    r"(?:政策|通知|办法|实施细则|官方|政务服务|政府|医保局|人社局)",
]
FACT_PATTERNS_TONGJIAN = [
    r"《资治通鉴》", r"司马光", r"臣光曰", r"卷[一二三四五六七八九十百零〇0-9]{1,8}",
    r"(?:周|秦|汉|魏|晋|宋|齐|梁|陈|隋|唐|后梁|后唐|后晋|后汉|后周)纪",
    r"(?:前)?\d{1,4}年", r"(?:皇帝|太子|丞相|将军|刺史|太守|尚书|司徒|司马)",
]
FACT_PATTERNS_FASHION = [
    r"\d+(?:\.\d+)?\s*(?:cm|厘米|元|块|%|码)",
    r"(?:西装|大衣|针织|衬衫|半裙|长裙|短裙|直筒裤|阔腿裤|牛仔裤|乐福鞋|运动鞋|靴|包)",
    r"(?:肩线|腰线|衣长|裤型|廓形|垂感|材质|叠穿|配色|冷暖|明度|比例)",
    r"(?:韩系|韩国|日系|日本|机场穿搭|Lookbook|Campaign|Press Kit)",
]
FACT_PATTERNS_JINGYUN = [
    r"\d+(?:\.\d+)?%", r"\d+\s*(?:岁|年|个月|万元|元|人|次|天|小时)",
    r"(?:婚姻|离婚|抚养|财产|收入|全职妈妈|职场|父母|养老|围绝经期|女性|家庭)",
    r"(?:民法典|法院|统计局|卫健|妇联|WHO|UN Women|ILO|OECD)",
]
FACT_PATTERNS_PARENTING = [
    r"\\d+(?:\\.\\d+)?%", r"\\d+(?:\\.\\d+)?\\s*(?:元|万|年|月|天|周|岁|个月)",
    r"(?:20\\d{2}|19\\d{2})[年/-]",
    r"(?:生育|孕产|产检|津贴|育儿补贴|儿童医保|居民医保|职工医保|医疗|托育|多子女|二孩|三孩|购房补贴)",
    r"(?:申请|申领|参保|结算|报销|审核|材料|截止|户籍|异地|官方|政策|政府|服务包)",
    r"(?:卫健|医保局|住房|人社|发放|补助|待遇|补贴|支付)",
]
JINGYUN_FABRICATED_FIRST_PERSON_PATTERNS = [
    r"我老公", r"我丈夫", r"我老婆", r"我女儿", r"我儿子",
    r"我离婚(?:那年|以后|之后|时)", r"我结婚(?:那年|以后|之后|时)",
    r"我婆婆", r"我公公", r"我做咨询时", r"我的来访者",
    r"我的一个闺蜜", r"我有一个闺蜜", r"我的一个朋友跟我说",
]

FACT_PATTERNS_QIEZHI = [
    r"《[^》]{2,30}》", r"毛泽东",
    r"《实践论》|《矛盾论》|《论持久战》|《反对本本主义》",
    r"\d+\s*(?:步|类|条|次|个|点)",
]

def strip_production_markup(md: str) -> str:
    text = re.sub(r"<!--\s*ZZTJ_SOURCE\s*\{[\s\S]*?\}\s*-->", "", md, flags=re.S)
    text = re.sub(r"<!--\s*FASHION_SOURCE\s*\{[\s\S]*?\}\s*-->", "", text, flags=re.S)
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
    elif profile_key == "jingyun":
        fact_patterns = FACT_PATTERNS_JINGYUN
        stance_patterns = STANCE_PATTERNS_JINGYUN
    elif profile_key == "fashion":
        fact_patterns = FACT_PATTERNS_FASHION
        stance_patterns = STANCE_PATTERNS_FASHION
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

    if profile_key == "jingyun":
        first_person_hits = count_matches(JINGYUN_FABRICATED_FIRST_PERSON_PATTERNS, body)
        if first_person_hits:
            hard_failures.append(
                f"检测到 {first_person_hits} 处疑似虚构的第一人称私人经历；静筠日记禁止凭空编造婚姻、孩子、离婚、咨询或朋友经历"
            )

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
    if args.profile in ("parenting", "business_story"):
        heading = next(
            (line[2:].strip() for line in article.read_text(encoding="utf-8").splitlines()
             if line.startswith("# ")), ""
        )
        editorial = assess_editorial_title(args.profile, article, heading)
        result["editorial_title_guard"] = editorial
        if editorial["status"] == "FAIL":
            result["hard_failures"].extend(editorial["reasons"])
            result["status"] = "FAIL"
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
