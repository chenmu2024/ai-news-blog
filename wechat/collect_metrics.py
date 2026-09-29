from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

import requests

APP_ID = os.environ["WECHAT_APP_ID"].strip()
APP_SECRET = os.environ["WECHAT_APP_SECRET"].strip()
PROXY_URL = (os.getenv("PROXY_URL") or "").strip()
API = "https://api.weixin.qq.com"
TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path("wechat/metrics")
RAW_DIR = ROOT / "raw"
DAILY_DIR = ROOT / "daily"
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None


def log(*parts):
    print(*parts, flush=True)


def request(method: str, url: str, **kwargs):
    r = requests.request(method, url, proxies=PROXIES, timeout=45, **kwargs)
    r.raise_for_status()
    return r


def get_token() -> str:
    r = request(
        "GET",
        API + "/cgi-bin/token",
        params={
            "grant_type": "client_credential",
            "appid": APP_ID,
            "secret": APP_SECRET,
        },
    )
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("获取 access_token 失败: " + json.dumps(data, ensure_ascii=False))
    return token


def datacube(token: str, endpoint: str, begin: str, end: str) -> dict:
    payload = json.dumps(
        {"begin_date": begin, "end_date": end},
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        r = request(
            "POST",
            f"{API}/datacube/{endpoint}",
            params={"access_token": token},
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        data = r.json()
    except Exception as exc:
        return {"_error": str(exc)}
    if isinstance(data, dict) and data.get("errcode") not in (None, 0):
        return {"_error": data}
    return data if isinstance(data, dict) else {"_error": "unexpected response", "_raw": data}


def list_of(resp: dict) -> list[dict]:
    value = resp.get("list", []) if isinstance(resp, dict) else []
    return value if isinstance(value, list) else []


def num(d: dict, key: str) -> int:
    try:
        return int(d.get(key, 0) or 0)
    except Exception:
        return 0


def sum_fields(rows: list[dict], keys: list[str]) -> dict:
    return {k: sum(num(x, k) for x in rows) for k in keys}


def pct(n: float, d: float) -> str:
    if not d:
        return "—"
    return f"{n / d * 100:.2f}%"


def safe_div(n: float, d: float):
    return None if not d else n / d


def load_previous_raw(exclude: str, limit: int = 7) -> list[dict]:
    rows = []
    if not RAW_DIR.exists():
        return rows
    for p in sorted(RAW_DIR.glob("*.json"), reverse=True):
        if p.stem == exclude:
            continue
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(rows) >= limit:
            break
    return rows


def aggregate_day(raw: dict) -> dict:
    read_rows = list_of(raw.get("user_read", {}))
    article_rows = list_of(raw.get("article_summary", {}))
    user_rows = list_of(raw.get("user_summary", {}))
    cum_rows = list_of(raw.get("user_cumulate", {}))

    fields = [
        "int_page_read_user",
        "int_page_read_count",
        "ori_page_read_user",
        "ori_page_read_count",
        "share_user",
        "share_count",
        "add_to_fav_user",
        "add_to_fav_count",
    ]
    base = sum_fields(read_rows if read_rows else article_rows, fields)
    base["new_user"] = sum(num(x, "new_user") for x in user_rows)
    base["cancel_user"] = sum(num(x, "cancel_user") for x in user_rows)
    base["net_user"] = base["new_user"] - base["cancel_user"]
    base["cumulate_user"] = max([num(x, "cumulate_user") for x in cum_rows] or [0])
    return base


def lifetime_articles(raw: dict) -> list[dict]:
    out = []
    totals = raw.get("article_total_7d", {})
    for pub_date, resp in totals.items():
        for article in list_of(resp):
            details = article.get("details") or []
            if not isinstance(details, list) or not details:
                continue
            details = sorted(details, key=lambda x: x.get("stat_date", ""))
            d = details[-1]
            item = {
                "publish_date": article.get("ref_date") or pub_date,
                "stat_date": d.get("stat_date"),
                "msgid": article.get("msgid", ""),
                "title": article.get("title", ""),
                "target_user": num(d, "target_user"),
                "read_user": num(d, "int_page_read_user"),
                "read_count": num(d, "int_page_read_count"),
                "share_user": num(d, "share_user"),
                "share_count": num(d, "share_count"),
                "fav_user": num(d, "add_to_fav_user"),
                "fav_count": num(d, "add_to_fav_count"),
                "from_session_user": num(d, "int_page_from_session_read_user"),
                "from_history_user": num(d, "int_page_from_hist_msg_read_user"),
                "from_feed_user": num(d, "int_page_from_feed_read_user"),
                "from_friends_user": num(d, "int_page_from_friends_read_user"),
                "from_other_user": num(d, "int_page_from_other_read_user"),
            }
            item["read_rate"] = safe_div(item["read_user"], item["target_user"])
            item["share_rate"] = safe_div(item["share_user"], item["read_user"])
            item["fav_rate"] = safe_div(item["fav_user"], item["read_user"])
            out.append(item)
    return sorted(out, key=lambda x: (x["publish_date"], x["read_user"]), reverse=True)


def render_report(target: str, raw: dict, previous: list[dict]) -> str:
    daily = aggregate_day(raw)
    prev_aggs = [aggregate_day(x) for x in previous]
    prev_reads = [x["int_page_read_user"] for x in prev_aggs if x["int_page_read_user"] > 0]
    prev_share_rates = [
        x["share_user"] / x["int_page_read_user"]
        for x in prev_aggs
        if x["int_page_read_user"] > 0
    ]
    baseline_read = mean(prev_reads) if prev_reads else None
    baseline_share = mean(prev_share_rates) if prev_share_rates else None
    article_rows = sorted(
        list_of(raw.get("article_summary", {})),
        key=lambda x: num(x, "int_page_read_user"),
        reverse=True,
    )
    lifetime = lifetime_articles(raw)

    lines = [
        f"# 微信公众号数据复盘 — {target}",
        "",
        f"> 采集时间：{raw.get('collected_at', '')}",
        "",
        "## 1. 昨日总体表现",
        "",
        f"- 图文阅读人数：**{daily['int_page_read_user']}**",
        f"- 图文阅读次数：**{daily['int_page_read_count']}**",
        f"- 分享人数 / 次数：**{daily['share_user']} / {daily['share_count']}**",
        f"- 收藏人数 / 次数：**{daily['add_to_fav_user']} / {daily['add_to_fav_count']}**",
        f"- 分享率（分享人数÷阅读人数）：**{pct(daily['share_user'], daily['int_page_read_user'])}**",
        f"- 收藏率（收藏人数÷阅读人数）：**{pct(daily['add_to_fav_user'], daily['int_page_read_user'])}**",
        f"- 新增关注：**{daily['new_user']}**",
        f"- 取消关注：**{daily['cancel_user']}**",
        f"- 净增关注：**{daily['net_user']}**",
        f"- 累计关注：**{daily['cumulate_user'] or '—'}**",
        "",
    ]

    if baseline_read is not None:
        delta = (daily["int_page_read_user"] - baseline_read) / baseline_read if baseline_read else 0
        lines += [
            "## 2. 与最近可用基线相比",
            "",
            f"- 最近 {len(prev_reads)} 个有数据日平均阅读人数：**{baseline_read:.1f}**",
            f"- 昨日阅读人数相对基线：**{delta:+.1%}**",
        ]
        if baseline_share is not None and daily["int_page_read_user"] > 0:
            current = daily["share_user"] / daily["int_page_read_user"]
            lines.append(f"- 最近基线分享率：**{baseline_share:.2%}**；昨日：**{current:.2%}**")
        lines.append("")

    lines += ["## 3. 昨日被阅读的文章", ""]
    if article_rows:
        for i, x in enumerate(article_rows[:10], 1):
            title = x.get("title") or "(无标题)"
            read_user = num(x, "int_page_read_user")
            read_count = num(x, "int_page_read_count")
            share_user = num(x, "share_user")
            fav_user = num(x, "add_to_fav_user")
            lines.append(
                f"{i}. **{title}** — 阅读人数 {read_user}，阅读次数 {read_count}，"
                f"分享人数 {share_user}，收藏人数 {fav_user}，分享率 {pct(share_user, read_user)}"
            )
    else:
        lines.append("- 暂无逐篇图文数据；可能是阅读量过低、账号权限限制，或该发布方式未返回逐篇数据。")
    lines.append("")

    lines += ["## 4. 最近7天发布文章累计表现", ""]
    if lifetime:
        for i, x in enumerate(lifetime[:12], 1):
            lines.append(
                f"{i}. **{x['title'] or '(无标题)'}**（{x['publish_date']}）— "
                f"累计阅读人数 {x['read_user']}，分享人数 {x['share_user']}，收藏人数 {x['fav_user']}，"
                f"阅读/目标用户 {pct(x['read_user'], x['target_user'])}，"
                f"分享率 {pct(x['share_user'], x['read_user'])}"
            )
    else:
        lines.append("- 暂无最近7天逐篇累计数据。")
    lines.append("")

    lines += ["## 5. 自动判断", ""]
    if daily["int_page_read_user"] == 0:
        lines.append("- **样本不足**：昨日接口未返回有效阅读人数，今天不要据此大幅调整选题或写法。")
    else:
        if baseline_read is None:
            lines.append("- **正在建立基线**：先连续采集 7–14 天，再判断题材和结构的稳定差异。")
        else:
            delta = (daily["int_page_read_user"] - baseline_read) / baseline_read if baseline_read else 0
            if delta >= 0.25:
                lines.append("- **阅读明显高于近期基线**：保留这类选题/标题结构，下一篇可做相邻主题验证。")
            elif delta <= -0.25:
                lines.append("- **阅读明显低于近期基线**：先检查标题、发布时间和开头，并等待更多样本。")
            else:
                lines.append("- **阅读处于近期正常区间**：暂不因单日波动改变主线。")
        share_rate = safe_div(daily["share_user"], daily["int_page_read_user"])
        if share_rate is not None and baseline_share is not None:
            if share_rate >= baseline_share * 1.25:
                lines.append("- **分享效率高于近期基线**：这类可执行项目、清单和方法型内容值得继续强化。")
            elif share_rate <= baseline_share * 0.75:
                lines.append("- **分享效率偏低**：下一篇减少新闻背景，把具体项目、数据和行动步骤提前。")

    lines += [
        "",
        "## 6. 给下一篇文章的使用规则",
        "",
        "- 优先看 **7–14天重复出现的模式**，不要追单日噪音。",
        "- 阅读高但分享低：优化实用性、可保存性和项目拆解深度。",
        "- 阅读低但分享高：选题可能偏窄，但内容价值高，可优化标题与分发。",
        "- 阅读和分享同时高：作为后续选题簇继续扩展。",
        "- 新增关注/净增明显改善时，记录当天主题、标题结构和开头方式。",
        "",
        "## 7. 接口状态",
        "",
    ]

    for key in ["article_summary", "user_read", "user_share", "user_summary", "user_cumulate"]:
        resp = raw.get(key, {})
        if isinstance(resp, dict) and "_error" in resp:
            lines.append(f"- {key}: **失败** — {resp['_error']}")
        else:
            lines.append(f"- {key}: **成功**")

    failures = sum(
        1
        for resp in raw.get("article_total_7d", {}).values()
        if isinstance(resp, dict) and "_error" in resp
    )
    lines.append(f"- article_total_7d: **{7 - failures}/7 天成功**")
    lines.append("")
    lines.append("> 说明：微信公众号图文数据接口存在统计门槛和时间窗口；接口没有返回的数据不会被程序臆测。")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD；默认采集昨日（Asia/Shanghai）")
    args = parser.parse_args()

    today = datetime.now(TZ).date()
    target_date = date.fromisoformat(args.date) if args.date else today - timedelta(days=1)
    if target_date >= today:
        raise SystemExit("只能采集昨日或更早日期")
    target = target_date.isoformat()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    log("[METRICS] target:", target)
    log("[PROXY]", "enabled" if PROXY_URL else "direct")

    token = get_token()
    raw = {
        "date": target,
        "collected_at": datetime.now(TZ).isoformat(),
        "article_summary": datacube(token, "getarticlesummary", target, target),
        "user_read": datacube(token, "getuserread", target, target),
        "user_share": datacube(token, "getusershare", target, target),
        "user_summary": datacube(token, "getusersummary", target, target),
        "user_cumulate": datacube(token, "getusercumulate", target, target),
        "article_total_7d": {},
    }

    for days_ago in range(7):
        ds = (target_date - timedelta(days=days_ago)).isoformat()
        raw["article_total_7d"][ds] = datacube(token, "getarticletotal", ds, ds)

    raw_path = RAW_DIR / f"{target}.json"
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    previous = load_previous_raw(target, limit=7)
    report = render_report(target, raw, previous)
    report_path = DAILY_DIR / f"{target}.md"
    report_path.write_text(report, encoding="utf-8")

    latest_json = {
        "date": target,
        "summary": aggregate_day(raw),
        "lifetime_articles": lifetime_articles(raw),
        "source_file": str(raw_path),
        "report_file": str(report_path),
        "collected_at": raw["collected_at"],
    }
    (ROOT / "latest.json").write_text(
        json.dumps(latest_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ROOT / "latest.md").write_text(report, encoding="utf-8")

    log("[SUCCESS] metrics saved:", raw_path)
    log("[SUCCESS] report saved:", report_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("[ERROR]", repr(exc))
        sys.exit(1)
