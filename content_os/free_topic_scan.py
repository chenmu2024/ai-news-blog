"""Free public topic discovery for the seven WeChat directions.

Never asserts that public search results are 'viral' without independent
ranking/read-count evidence; this tool does not publish or generate articles.
No API key, cookies, account login, paid crawling or CAPTCHA bypass.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from public_rankings import find_public_rankings, related_rankings

# Recovery trigger: maintain a fresh Asia/Shanghai daily public discovery archive.
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "content_os" / "topic-intelligence"
LOCAL = ZoneInfo("Asia/Shanghai")
PROFILES = {
    "qiezhi": {"query": "毛泽东选集 人生 思想 公众号", "image": "history books"},
    "wechat": {"query": "AI Agent 独立开发 SaaS 一人公司 公众号", "image": "artificial intelligence computer"},
    "business": {"query": "社保 医保 公积金 失业金 劳动者 福利政策 公众号", "image": "public service office"},
    "zizhitongjian": {"query": "资治通鉴 历史 人性 管理 公众号", "image": "historical books"},
    "parenting": {"query": "育儿补贴 生育津贴 儿童医保 托育 家庭政策 公众号", "image": "family child care"},
    "jingyun": {"query": "女性 中年 婚姻 职场 公众号", "image": "women street life"},
    "fashion": {"query": "2026 女明星 Jisoo 张员瑛 杨幂 机场穿搭 公众号", "image": "celebrity airport fashion"},
}
# Secondary free discovery queries diversify subject/author coverage; they are
# NOT proof that a headline is popular or that an indexed date is publication.
SUPPLEMENTARY_QUERIES = {
    "qiezhi": "毛选 调查研究 工作 方法 公众号",
    "wechat": "AI创业 SaaS 独立开发者 真实案例 公众号",
    "business": "灵活就业 养老金 租房 人才补贴 申请条件 官方 公众号",
    "zizhitongjian": "资治通鉴 帝王 决策 历史故事 公众号",
    "parenting": "孕产 生育保险 多子女购房补贴 申请 户籍 官方 公众号",
    "jingyun": "中年女人 母女 经济独立 婚姻 公众号",
    "fashion": "女明星 Jisoo Jennie 宋慧乔 刘亦菲 机场 穿搭 公众号",
}
UNTRUSTED_GENERIC_TITLES = frozenset({
    "微信公众平台", "微信公众平台 - 微信公众平台", "微信公众平台 - 微信公众平台",
    "微信公众号", "微信公众号登录", "微信公众平台登录",
    "Weixin - 微信公众平台 - 微信公众平台",
})


def is_useful_discovery(item):
    title = re.sub(r"\s+", " ", (item.get("title") or "")).strip()
    url = item.get("url") or ""
    # Explicit old-year headlines can inform background research but must not
    # be promoted to a current audience-interest sample.
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", title)]
    stale_year = any(y < datetime.now(LOCAL).year - 1 for y in years)
    wechat_login = bool(re.search(
        r"(?i)^(?:weixin\s*[-—:]\s*)?微信公众平台\s*[-—:]\s*微信公众平台$",
        title,
    ))
    return (len(title) >= 6 and title not in UNTRUSTED_GENERIC_TITLES
            and not stale_year and not wechat_login
            and urlparse(url).scheme == "https")


def title_mechanisms(title):
    """Editorial *hypotheses* only; never treat these as verified popularity."""
    result = []
    if re.search(r"[？?]", title):
        result.append("悬念提问")
    if re.search(r"为什么|却|竟然|反而|没想到|但是|然而", title):
        result.append("反差转折")
    if re.search(r"\d+[个条种年]|\d+\s*[招步点]", title):
        result.append("数字结构")
    if re.search(r"孩子|家长|妈妈|普通人|女人", title):
        result.append("具体人群")
    if re.search(r"公司|品牌|收购|融资|利润", title):
        result.append("公司事件")
    return result[:3] or ["主题直述"]


UA = "ContentOS-TopicResearch/1.0 (public discovery only)"
LIMIT_BYTES = 700_000


def fetch(url):
    p = urlparse(url)
    if p.scheme != "https" or p.hostname not in {
        "weixin.sogou.com", "news.google.com", "commons.wikimedia.org", "weixinhost.com", "www.bing.com"
    }:
        raise ValueError("Source host not allowed")
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urlopen(req, timeout=10) as r:
        content = r.read(LIMIT_BYTES + 1)
        if len(content) > LIMIT_BYTES:
            raise ValueError("Response too large")
        return content.decode(r.headers.get_content_charset() or "utf-8", errors="replace")


class WechatAnchorParser(HTMLParser):
    """Limit capture to anchors in article title H3; no generic external links."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.active = None
        self.articles = []

    def handle_starttag(self, tag, attrs):
        if tag == "h3":
            self.depth += 1
        if tag == "a" and self.depth and self.active is None:
            attr = dict(attrs)
            href = urljoin("https://weixin.sogou.com", html.unescape(attr.get("href", "")))
            host = (urlparse(href).hostname or "").lower()
            if host in ("weixin.sogou.com", "mp.weixin.qq.com"):
                self.active = {"title": [], "url": href}

    def handle_data(self, text):
        if self.active is not None:
            self.active["title"].append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.active is not None:
            title = re.sub(r"\s+", " ", "".join(self.active["title"])).strip()
            if len(title) >= 4:
                self.articles.append({"title": title[:180], "url": self.active["url"],
                                      "platform": "sogou_wechat_index",
                                      "published_at": None, "account": None, "heat": None,
                                      "heat_verified": False,
                                      "verification": "discoverable title only; no reading-count evidence"})
            self.active = None
        if tag == "h3" and self.depth:
            self.depth -= 1


def wechat_results(query, limit=8):
    url = "https://weixin.sogou.com/weixin?" + urlencode({"type": 2, "query": query})
    parser = WechatAnchorParser()
    raw = fetch(url)
    if "验证码" in raw and not parser.articles:
        raise ValueError("Sogou verification challenge; not bypassed")
    parser.feed(raw)
    return parser.articles[:limit]


def news_index_results(query, limit=8):
    url = "https://news.google.com/rss/search?" + urlencode({
        "q": "site:mp.weixin.qq.com " + query,
        "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"})
    root = ET.fromstring(fetch(url))
    out = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:
            out.append({"title": title[:180], "url": link, "platform": "google_news_index",
                        "published_at": None, "indexed_at": item.findtext("pubDate"), "account": None,
                        "heat": None, "heat_verified": False,
                        "verification": "RSS index date is not original WeChat article publication date"})
    return out



# Independent, no-login source for factual topic candidates; *not* WeChat traffic.
# If Google News's WeChat index and Sogou go down simultaneously, this offers
# a second provider's headlines. Never count these as WeChat articles or heat.
BING_FALLBACK_QUERIES = {
    "qiezhi": "学习 方法 调查研究 读书",
    "wechat": "人工智能 Agent SaaS 创业 公司",
    "business": "职工医保 社保 公积金 失业金 申领 政策",
    "zizhitongjian": "资治通鉴 历史 人物 决策",
    "parenting": "育儿补贴 生育津贴 儿童医保 托育补助 政策",
    "jingyun": "女性 职场 婚姻 家庭",
    "fashion": "女明星 机场 时装周 造型 杨幂 张员瑛 Jisoo 2026",
}


def bing_news_results(query, limit=6):
    url = "https://www.bing.com/news/search?" + urlencode({"q": query, "format": "rss"})
    root = ET.fromstring(fetch(url))
    rows = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link or not is_useful_discovery({"title": title, "url": link}):
            continue
        rows.append({
            "title": title[:180], "url": link,
            "platform": "bing_news_rss_non_wechat",
            "published_at": None, "indexed_at": item.findtext("pubDate"),
            "account": None, "heat": None, "heat_verified": False,
            "verification": "third-party news RSS, not a WeChat original, "
                            "not an article reading count or verified popularity",
            "reference_only": True,
        })
    return rows[:limit]



def general_news_results(query, limit=6):
    """Third-tier news RSS candidate stream; never a WeChat popularity source."""
    url = "https://news.google.com/rss/search?" + urlencode({
        "q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"
    })
    root = ET.fromstring(fetch(url))
    rows = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not is_useful_discovery({"title": title, "url": link}):
            continue
        rows.append({
            "title": title[:180], "url": link,
            "platform": "google_news_general_non_wechat",
            "published_at": None, "indexed_at": item.findtext("pubDate"),
            "account": None, "heat": None, "heat_verified": False,
            "verification": "general news discovery only; not a WeChat article "
                            "or independently verified popularity",
            "reference_only": True,
        })
    return rows



def commons_images(query, limit=5):
    url = "https://commons.wikimedia.org/w/api.php?" + urlencode({
        "action": "query", "generator": "search", "gsrsearch": "filetype:bitmap " + query,
        "gsrnamespace": 6, "gsrlimit": limit * 2, "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": 800, "format": "json"})
    parsed = json.loads(fetch(url))
    result = []
    for page in parsed.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        img_url = info.get("thumburl") or info.get("url")
        source_url = info.get("descriptionurl")
        if not img_url or not source_url:
            continue
        result.append({"title": page.get("title"), "image_url": img_url, "source_page_url": source_url,
                       "license_url": meta.get("LicenseUrl", {}).get("value"),
                       "creator": re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", ""))[:150],
                       "rights_verified": False, "requires_manual_license_review": True,
                       "usage": "illustrative inspiration only; never infer actual celebrity outfit"})
    return result[:limit]


def scan(profile, max_items=8, with_images=False, public_rankings=None, use_extra_public_fallback=False):
    cfg = PROFILES[profile]
    rows = []
    statuses = {}
    for platform, func in [
        ("wechat", wechat_results),
        ("google_news_index", news_index_results),
    ]:
        # The second request is a fallback only if the first query has fewer
        # than five usable titles. Failed sources are isolated by profile.
        source_rows = []
        attempts = []
        for query in [cfg["query"], SUPPLEMENTARY_QUERIES[profile]]:
            if len(source_rows) >= 5:
                break
            try:
                discovered = [x for x in func(query, limit=max_items) if is_useful_discovery(x)]
                source_rows.extend(discovered)
                attempts.append({"query": query, "status": "ok", "count": len(discovered)})
            except (ValueError, OSError, ET.ParseError) as exc:
                attempts.append({"query": query, "status": "error", "message": str(exc)[:150]})
        rows.extend(source_rows)
        statuses[platform] = {
            "status": "ok" if source_rows else ("error" if any(x["status"] == "error" for x in attempts) else "empty"),
            "count": len(source_rows), "attempts": attempts,
        }
    seen, unique = set(), []
    for item in rows:
        key = item["url"].split("#")[0]
        # RSS headlines can repeat; canonical URL is not always available.
        title_key = re.sub(r"\W+", "", item.get("title", "").casefold())
        if key not in seen and ("t:" + title_key) not in seen:
            seen.add(key)
            seen.add("t:" + title_key)
            item["title_mechanisms"] = title_mechanisms(item["title"])
            unique.append(item)
    images = []
    if with_images:
        try:
            images = commons_images(cfg["image"])
            statuses["images"] = {"status": "ok" if images else "empty", "count": len(images)}
        except (ValueError, OSError) as exc:
            statuses["images"] = {"status": "error", "message": str(exc)[:200]}

    # A complete failure of WeChat indexing must not block original reporting.
    # Fallback news is kept OUTSIDE the WeChat samples and verified heat gate.
    fallback_signals = []
    missing_wechat_samples = len(unique) < 5
    missing_independent_heat = sum(bool(x.get("heat_verified")) for x in unique) < 2
    if use_extra_public_fallback and (missing_wechat_samples or missing_independent_heat):
        # Two independent public provider families, neither counted as WeChat.
        for platform, discovery in [
            ("bing_news_fallback", bing_news_results),
            ("general_news_fallback", general_news_results),
        ]:
            try:
                candidates = discovery(BING_FALLBACK_QUERIES[profile], limit=6)
                statuses[platform] = {
                    "status": "ok" if candidates else "empty",
                    "count": len(candidates),
                    "note": "Non-WeChat news clues only; facts require primary verification.",
                }
                if candidates:
                    fallback_signals = candidates
                    break
            except (ValueError, OSError, ET.ParseError) as exc:
                statuses[platform] = {"status": "error", "count": 0,
                                      "message": str(exc)[:160]}
    else:
        statuses["bing_news_fallback"] = {"status": "not_needed", "count": 0}
        statuses["general_news_fallback"] = {"status": "not_needed", "count": 0}

    # Strict: only publicly independently verified rankings/read counts can
    # satisfy heat evidence; no guessed readings or account names.
    heat_count = sum(bool(item.get("heat_verified")) for item in unique)
    ranking_matches = related_rankings(profile, public_rankings or [], limit=6)
    statuses["public_rankings"] = {"status": "ok" if ranking_matches else "no_profile_match",
                                    "count": len(ranking_matches)}
    # A topical headline on a third-party 10万+ list is NOT an official view
    # count and not necessarily the same article as a Sogou search hit.
    return {"profile": profile, "query": cfg["query"], "sample_count": len(unique),
            "heat_evidence_count": heat_count, "public_ranking_signal_count": len(ranking_matches),
            "public_ranking_signals": ranking_matches,
            "required_samples": 5, "required_heat_evidence": 2,
            "topic_gate": "research_ready" if len(unique) >= 5 and heat_count >= 2 else "insufficient_evidence",
            "writing_allowed": True,
            "writing_mode": "heat_verified" if len(unique) >= 5 and heat_count >= 2 else "fact_verified_source_fallback",
            "candidate_confidence": "source_verified" if heat_count >= 2 else "indexed_title_only",
            "production_rule": "Never block daily original writing due to insufficient public heat; use verified primary facts, title dedup, original-source and image gates.",
            "sources": statuses, "articles": unique[:max_items * 2],
            "fallback_news_signals": fallback_signals, "fallback_news_count": len(fallback_signals),
            "image_candidates": images,
            "note": "Indexed titles and third-party list positions are not independently verified WeChat reading counts; topic gate stays conservative."}



def attach_fallback_references(report: dict, prior: dict, today: str) -> None:
    """Keep earlier *labeled* clues if a later no-cost scan loses every source.

    Never increase today's live sample or verified popularity counters.
    Same-day cached headlines come from earlier *actual* scanning today;
    yesterday's headlines are historical ideas, never today's report.
    """
    previous_day = prior.get("local_date")
    if not isinstance(previous_day, str) or previous_day > today:
        return
    for profile, item in report["profiles"].items():
        if item["sample_count"] > 0 or item.get("fallback_news_count", 0) > 0:
            continue
        old = prior.get("profiles", {}).get(profile, {})
        hints = [x for x in old.get("articles", []) if is_useful_discovery(x)][:5]
        if not hints:
            hints = [x for x in old.get("same_day_cached_references", []) if
                     is_useful_discovery(x)][:5]
        if not hints:
            continue
        if previous_day == today:
            item["same_day_cached_references"] = hints
            item["same_day_cache_generated_at"] = prior.get("generated_at")
            item["sources"]["same_day_cache"] = {
                "status": "cached_earlier_today_not_new_fetch",
                "count": len(hints), "date": today
            }
        else:
            item["prior_reference_date"] = previous_day
            item["prior_references"] = hints
            item["sources"]["stale_reference"] = {
                "status": "historical_reference_only", "count": len(hints),
                "date": previous_day,
            }



def render(report):
    ranking = report.get("public_ranking_discovery", {})
    lines = ["# 七公众号｜免费公开选题发现", "", "生成时间：" + report["generated_at"], "",
             "**研究证据，不是已完成的微信热门验证。** 缺少阅读量或公开榜单证据时，不得认定爆款。",
             "公开榜单新鲜度：" + ranking.get("freshness_status", "unverified"), "",
             ranking.get("warning", ""), ""]
    for key, entry in report["profiles"].items():
        lines += ["## " + key, "", "状态：" + entry["topic_gate"] +
                  "；样本 " + str(entry["sample_count"]) +
                  "；已核实热度证据 " + str(entry["heat_evidence_count"]) + "/2",
                  "写作模式：" + entry.get("writing_mode", "unverified") +
                  "；允许写作：" + str(entry.get("writing_allowed", False)) +
                  "（热度不足时只使用可核实的官方或原始来源，不宣称微信爆款）", ""]
        for item in entry["articles"]:
            lines.append("- [" + item["title"].replace("]", "") + "](" + item["url"] + ")"
                         + "（" + item["platform"] + "；热度：未知）")
        if not entry["articles"]:
            lines.append("- 未获取有效公开样本；不代表该类别没有热门文章。")
        if entry.get("fallback_news_signals"):
            lines.extend(["", "**独立新闻RSS备用线索（非微信文章、非热门证据）：**"])
            for item in entry["fallback_news_signals"]:
                lines.append("- [" + item["title"].replace("]", "") + "](" + item["url"] + ")"
                             + "（免费新闻RSS备用线索；并非微信热度，事实仍需核验）")
        if entry.get("same_day_cached_references"):
            lines.extend(["", "**当天较早扫描缓存：本轮外部源不可用，仍不计新的热度证据。**"])
            for item in entry["same_day_cached_references"]:
                lines.append("- [" + item["title"].replace("]", "") + "](" + item["url"] + ")"
                             + "（同日早些时候扫描，当前未重新核验）")
        if entry.get("prior_references"):
            lines.extend(["", "**旧日线索：仅供选题发散，严禁冒充当天扫描：** " +
                          entry.get("prior_reference_date", "unknown")])
            for item in entry["prior_references"]:
                lines.append("- [" + item["title"].replace("]", "") + "](" + item["url"] + ")"
                             + "（历史参考，热度未知）")

        lines += ["", "**第三方公开榜单（仅榜单声称热度，非文章阅读数核验）：** " +
                  str(entry.get("public_ranking_signal_count", 0)), ""]
        for rank in entry.get("public_ranking_signals", []):
            lines.append("- [" + rank["headline"].replace("]", "") + "](" + rank["ranking_page"] + ")"
                         + "；来源：侯斯特工坊；榜单日期：" + rank["ranking_date"] +
                         "；位置：" + str(rank["rank"]) + "；原文阅读量：未核验")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["all", *PROFILES], default="all")
    ap.add_argument("--images", action="store_true", help="Discover images; never auto-publish them")
    args = ap.parse_args()
    targets = PROFILES.keys() if args.profile == "all" else [args.profile]
    today = datetime.now(LOCAL).date().isoformat()
    # Previous data is useful as a *stale reference* only, never as today's scan.
    prior_report = {}
    try:
        prior_report = json.loads((OUTPUT / "latest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        prior_report = {}
    public_ranking_data = find_public_rankings(fetch, today=datetime.now(LOCAL).date(),
                                               window_days=5, max_successful_days=2)
    report = {"generated_at": datetime.now(LOCAL).isoformat(),
              "local_date": datetime.now(LOCAL).date().isoformat(),
              "monetary_cost": "no paid API", "auto_publish": False,
              "public_ranking_discovery": {
                  "status": public_ranking_data["status"],
                  "pages_found": public_ranking_data["pages_found"],
                  "errors": public_ranking_data["errors"],
                  "freshness_status": public_ranking_data["freshness_status"],
                  "daily_overlap_checks": public_ranking_data["daily_overlap_checks"],
                  "independent_recent_viral_evidence": False,
                  "warning": public_ranking_data["warning"]},
              "profiles": {key: scan(key, with_images=args.images,
                                    public_rankings=public_ranking_data["entries"],
                                    use_extra_public_fallback=True) for key in targets}}
    attach_fallback_references(report, prior_report, today)
    report["all_live_sources_unavailable"] = all(
        item["sample_count"] == 0 and item.get("fallback_news_count", 0) == 0
        for item in report["profiles"].values()
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (OUTPUT / (report["local_date"] + ".json")).write_text(payload, encoding="utf-8")
    (OUTPUT / "latest.json").write_text(payload, encoding="utf-8")
    text = render(report)
    (OUTPUT / (report["local_date"] + ".md")).write_text(text, encoding="utf-8")
    (OUTPUT / "latest.md").write_text(text, encoding="utf-8")
    print(json.dumps({"date": report["local_date"], "statuses": {
        k: v["topic_gate"] for k, v in report["profiles"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
