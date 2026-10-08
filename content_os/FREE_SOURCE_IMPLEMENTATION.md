# Zero-paid-API source research integration

Read-only script: `python content_os/free_topic_scan.py --profile all --images`.

- Daily research archive: `content_os/topic-intelligence/YYYY-MM-DD.json/.md`.
- Latest research: `content_os/topic-intelligence/latest.json/.md`.
- GitHub Actions daily 06:10 Asia/Shanghai (best effort schedule).
- Searches public Sogou WeChat article index and Google News index of
  `mp.weixin.qq.com` references. Source failures are explicit, with no
  login, paid browser service, cookies, CAPTCHAs, or hidden bypass.
- Image candidate search uses Wikimedia Commons metadata with license URL and
  artist/source links; candidates **must be reviewed** before publication.
- No generated reading counts, fake rank or hallucinated account names.
- Research status stays **insufficient_evidence** until 5 valid articles and
  2 independently verified heat signals are present. This scanner has no
  read-count API so it does not manufacture successful topic gates.
- Existing articles, fixed-source gates (Mao/资治通鉴), min 5 fashion images,
  title policies and WeChat draft flows are untouched.
- This is a data-discovery layer; actual article selection remains downstream.

```bash
python -m unittest discover -s content_os/tests -p test_free_topic_scan.py
python content_os/free_topic_scan.py --profile parenting
```

Do not interpret mere indexed occurrence as evidence of virality.

## Popularity evidence freshness review

The third-party Houst ranking list may repeat **identical article titles**
across consecutive dated pages. The collector now compares adjacent daily
lists and records `daily_overlap_checks`, `freshness_status`, and a warning.
If overlap is >=70% across two pages with at least ten titles each, the status
is `suspected_repeated_snapshot`. This is not proof of a fresh daily viral
ranking, or proof of each listed article's date.

Sources to check separately for **account-level** metrics (not automatically
ingested, and not counted as article-reading evidence):

- 清博指数指标口径说明: https://www.gsdata.cn/site/data-open?show=wx%2Ctt%2Cdy%2Cks
- 新榜公众号分类榜单: https://www.newrank.cn/ranklist/gongzhonghao/20/1/2025-12-12
  (this linked example is **historical**, not today's ranking)
- 微信爆款文章公开榜单来源: https://weixinhost.com/hotspot-radar/archive
- 微小榜公众号数据页面: https://wxrank.com/ (dynamic values may not load)

Only when a publicly accessible **contemporaneous** page exposes a named
account, metric, date and provenance should its account-level signal be
manually recorded. Never copy a channel's account-wide averages onto a
specific article. The script does not claim to fetch official read counts.

## Production-safe fallback and automation watchdog

The free discovery scan now has a second topic-specific query for each of the
seven directions, de-duplicates headline+URL, records source attempts, removes
generic WeChat login titles and never mistakes Google News RSS index timestamps
for WeChat article publication timestamps. It labels headline-hook
classification as **editorial heuristics** rather than popularity evidence.

`writing_allowed=True` is deliberately independent of `topic_gate`.
`fact_verified_source_fallback` permits producing a sourced, original
article despite insufficient evidence, but **does not** assert verified
popularity. The 5-sample/2-verified-heat threshold remains visible and
strict. It is not feasible to guarantee those signals for every category from
free, public, no-login WeChat interfaces.

GitHub Actions runs two free discovery windows (06:10 and 06:50 Shanghai).
Draft jobs are serial within each account and have a SHA-256 success receipt
preflight so restarting the workflow will not post the same archive again.
An independent health workflow runs at 10:15 and 13:15 Shanghai, verifies
all seven accounts and writes `content_os/daily-health/latest.json`. For a
missing receipt with an existing archive it can dispatch one safe additional
workflow attempt, but missing articles still require the upstream ChatGPT
writing task. Report failures rather than inventing an article or bypassing
source/image/quality gates.

A crash after WeChat has accepted a draft but before repository status was
committed cannot be safely distinguished from an unsent draft using the
repository alone. In that case check the WeChat draft list/ID before retrying.
Historical failure reports can remain even when a later run has succeeded.
