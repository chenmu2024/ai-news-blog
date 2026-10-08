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
