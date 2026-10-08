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

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "content_os" / "topic-intelligence"
LOCAL = ZoneInfo("Asia/Shanghai")
PROFILES = {
    "qiezhi": {"query": "毛泽东选集 人生 思想 公众号", "image": "history books"},
    "wechat": {"query": "AI Agent 独立开发 SaaS 一人公司 公众号", "image": "artificial intelligence computer"},
    "business": {"query": "商业故事 公司 品牌 公众号", "image": "business office"},
    "zizhitongjian": {"query": "资治通鉴 历史 人性 管理 公众号", "image": "historical books"},
    "parenting": {"query": "育儿 家庭教育 孩子 手机 作业 公众号", "image": "family reading"},
    "jingyun": {"query": "女性 中年 婚姻 职场 公众号", "image": "women street life"},
    "fashion": {"query": "日韩穿搭 明星穿搭 秋季 女装 公众号", "image": "fashion street style"},
}
UA = "ContentOS-TopicResearch/1.0 (public discovery only)"
LIMIT_BYTES = 700_000


def fetch(url):
    p = urlparse(url)
    if p.scheme != "https" or p.hostname not in {
        "weixin.sogou.com", "news.google.com", "commons.wikimedia.org", "weixinhost.com"
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
                        "published_at": item.findtext("pubDate"), "account": None,
                        "heat": None, "heat_verified": False,
                        "verification": "RSS indexed discovery; destination/publication not verified"})
    return out


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


def scan(profile, max_items=8, with_images=False, public_rankings=None):
    cfg = PROFILES[profile]
    rows = []
    statuses = {}
    for platform, func in [
        ("wechat", lambda: wechat_results(cfg["query"], limit=max_items)),
        ("google_news_index", lambda: news_index_results(cfg["query"], limit=max_items)),
    ]:
        try:
            found = func()
            rows.extend(found)
            statuses[platform] = {"status": "ok" if found else "empty", "count": len(found)}
        except (ValueError, OSError, ET.ParseError) as exc:
            statuses[platform] = {"status": "error", "message": str(exc)[:200]}
    seen, unique = set(), []
    for item in rows:
        key = item["url"].split("#")[0]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    images = []
    if with_images:
        try:
            images = commons_images(cfg["image"])
            statuses["images"] = {"status": "ok" if images else "empty", "count": len(images)}
        except (ValueError, OSError) as exc:
            statuses["images"] = {"status": "error", "message": str(exc)[:200]}

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
            "sources": statuses, "articles": unique[:max_items * 2], "image_candidates": images,
            "note": "Public ranked headlines are third-party claims, not official article reading-count measurements; topic gate stays conservative."}


def render(report):
    ranking = report.get("public_ranking_discovery", {})
    lines = ["# 七公众号｜免费公开选题发现", "", "生成时间：" + report["generated_at"], "",
             "**研究证据，不是已完成的微信热门验证。** 缺少阅读量或公开榜单证据时，不得认定爆款。",
             "公开榜单新鲜度：" + ranking.get("freshness_status", "unverified"), "",
             ranking.get("warning", ""), ""]
    for key, entry in report["profiles"].items():
        lines += ["## " + key, "", "状态：" + entry["topic_gate"] +
                  "；样本 " + str(entry["sample_count"]) +
                  "；已核实热度证据 " + str(entry["heat_evidence_count"]) + "/2", ""]
        for item in entry["articles"]:
            lines.append("- [" + item["title"].replace("]", "") + "](" + item["url"] + ")"
                         + "（" + item["platform"] + "；热度：未知）")
        if not entry["articles"]:
            lines.append("- 未获取有效公开样本；不代表该类别没有热门文章。")
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
                                    public_rankings=public_ranking_data["entries"]) for key in targets}}
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
