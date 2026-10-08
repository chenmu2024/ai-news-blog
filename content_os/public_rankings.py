"""Parse public third-party WeChat popularity rankings conservatively.

Records only third-party *claims* with traceable dated source URLs.
A ranking entry is not a verified official article reading count and does
not independently pass Content OS's article heat-evidence gate.
"""
from __future__ import annotations
from datetime import date, timedelta
from html.parser import HTMLParser
import re
from typing import Callable

SOURCE = "weixinhost.com"
MARKER = "微信10万+爆款文章"
CATEGORY_TERMS = {
    "qiezhi": ("思想", "人生", "读书", "心态", "情绪", "认知", "人性", "焦虑", "处世"),
    "wechat": ("人工智能", "智能体", "AI", "Agent", "SaaS", "一人公司", "独立开发", "大模型"),
    "business": ("公司", "企业", "品牌", "生意", "利润", "财报", "商战", "门店", "收入", "商业"),
    "zizhitongjian": ("资治通鉴", "古代", "皇帝", "朝代", "三国", "唐朝", "汉朝", "明朝", "帝王", "史书"),
    "parenting": ("孩子", "父母", "家长", "老师", "学校", "教育", "青春期", "作业", "育儿", "亲子"),
    "jingyun": ("女人", "女性", "中年", "婚姻", "情感", "老公", "婆婆", "职场", "钱难挣"),
    "fashion": ("穿搭", "衣服", "外套", "搭配", "女装", "裙", "日韩", "时尚"),
}

class Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = None
        self.entries = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and self.active is None:
            self.active = {"url": dict(attrs).get("href", ""), "pieces": []}

    def handle_data(self, data):
        if self.active is not None:
            self.active["pieces"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.active is not None:
            txt = re.sub(r"\s+", " ", "".join(self.active["pieces"])).strip()
            self.entries.append((txt, self.active["url"]))
            self.active = None


def extract_rankings(page_html, day, source_url):
    date_text = str(int(day[:4])) + "年" + str(int(day[5:7])) + "月" + str(int(day[8:10])) + "日"
    if MARKER not in page_html or date_text not in re.sub(r"<[^>]+>", "", page_html):
        raise ValueError("ranking marker or expected day absent; do not trust snapshot")
    parser = Anchors()
    parser.feed(page_html)
    entries, seen = [], set()
    for label, href in parser.entries:
        if "查看标题拆解" not in label:
            continue
        text = label.replace("查看标题拆解", "").strip()
        match = re.match(r"^0?(30|[12]\d|[1-9])\s*(.+)$", text)
        if not match:
            continue
        rank, headline = int(match.group(1)), match.group(2).strip()
        if rank > 30 or rank in seen or len(headline) < 5:
            continue
        seen.add(rank)
        entries.append({
            "headline": headline[:200], "rank": rank,
            "ranking_date": day, "ranking_page": source_url,
            "source_name": "侯斯特工坊",
            "source_type": "third_party_public_list",
            "source_claim": "source labels its list 微信10万+",
            "article_read_count": None, "article_url": None,
            "verified_article_read_count": False,
            "verification": "public ranking claim only; ranking page does not provide official count or original article URL",
        })
    return sorted(entries, key=lambda x: x["rank"])


def normalize_headline(value):
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def find_public_rankings(fetch: Callable[[str], str], today=None, window_days=5, max_successful_days=2):
    today = today or date.today()
    pages, errors, daily = [], [], {}
    for offset in range(1, min(7, window_days) + 1):
        day = (today - timedelta(days=offset)).isoformat()
        url = "https://weixinhost.com/hotspot-radar/" + day
        try:
            entries = extract_rankings(fetch(url), day, url)
            if entries:
                daily[day] = entries
                pages.extend(entries)
            else:
                errors.append({"day": day, "status": "empty"})
        except (ValueError, OSError) as exc:
            errors.append({"day": day, "status": "unavailable", "reason": str(exc)[:120]})
        if len(daily) >= max_successful_days:
            break

    # If two "daily" lists contain nearly identical titles, their dates do not
    # establish that the content itself was published or popular on those days.
    comparisons = []
    dates = sorted(daily, reverse=True)
    for day_a, day_b in zip(dates, dates[1:]):
        a = {normalize_headline(x["headline"]) for x in daily[day_a]}
        b = {normalize_headline(x["headline"]) for x in daily[day_b]}
        if min(len(a), len(b)) >= 10:
            comparisons.append({"dates": [day_a, day_b],
                                "overlap_ratio": round(len(a & b) / min(len(a), len(b)), 3)})
    suspicious = any(p["overlap_ratio"] >= 0.70 for p in comparisons)
    freshness_status = ("suspected_repeated_snapshot" if suspicious
                        else "distinct_daily_lists" if comparisons
                        else "unverifiable_single_day")
    return {
        "status": "ok" if daily else "unavailable",
        "pages_found": len(daily), "entries": pages, "errors": errors,
        "daily_overlap_checks": comparisons,
        "freshness_status": freshness_status,
        "independent_recent_viral_evidence": False,
        "warning": ("Daily-ranked titles substantially repeat. Treat list dates as page labels, "
                    "not verified publication dates or independent evidence of recent virality.")
                    if suspicious else "Third-party ranking claims still require original article verification."
    }


def related_rankings(profile, entries, limit=6):
    terms = CATEGORY_TERMS[profile]
    out = []
    seen_headlines = set()
    # Adjacent days may contain the same 24-hour headline.
    for entry in sorted(entries, key=lambda x: (-int(x["ranking_date"].replace("-", "")), x["rank"])):
        headline = entry["headline"].casefold()
        normalized_headline = "".join(ch for ch in headline if ch.isalnum())
        if normalized_headline in seen_headlines:
            continue
        seen_headlines.add(normalized_headline)
        matches = [term for term in terms if term.casefold() in headline]
        if not matches:
            continue
        r = dict(entry)
        r["matched_topic_terms"] = matches
        r["topic_match_basis"] = "literal headline keywords only; not a claim of article relevance or readership"
        out.append(r)
    return sorted(out, key=lambda r: (-len(r["matched_topic_terms"]), -int(r["ranking_date"].replace("-", "")), r["rank"]))[:limit]
