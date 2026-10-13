# Reading performance feedback

Fallback for accounts whose WeChat Datacube endpoints are unavailable or return `48001 api unauthorized`.

Append only **verified** observations to `manual.jsonl`. V5 can use views plus optional verified engagement metrics:

```json
{"profile":"business","date":"2026-10-10","title":"Example title","views":123,"likes":8,"shares":3,"comments":1,"open_rate":0.21,"source":"WeChat backend screenshot/manual observation"}
```

`views/likes/shares/comments` must be non-negative integers when present. `open_rate` must be a verified number from 0 to 1. Missing values stay null or are omitted.

If only a qualitative observation is known, keep `views` null and add a note. Never convert labels such as “better than usual” into an invented number.

```json
{"profile":"business","date":"2026-10-10","title":"Example title","views":null,"source":"manual observation","note":"relative performance only"}
```

The daily summarizer only computes numeric averages from verified integer `views`. It is advisory and should not change editorial direction from one or two samples.

Text notes are preserved in each profile's `qualitative_feedback` and passed to the next editorial shortlist. They never count as views. Standing editorial instructions and required responses to user feedback are kept in `content_os/editorial-feedback.json`; every new editorial review must address applicable active items.


Humanizer V5 joins these verified observations with archive/title/Humanizer evidence via `article_feedback_database.py`. It never infers missing metrics. Title and writing associations require minimum sample sizes before they are allowed into `account_learning_latest.json`.
