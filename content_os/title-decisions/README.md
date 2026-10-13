# Headline decision ledger

From 2026-10-11, the 07:00 editorial task should create
`content_os/title-decisions/YYYY-MM-DD.json` after drafting the seven articles.

Each profile must contain **exactly three unique headline candidates**. The
selected headline must be one of those three and must exactly equal that
profile's archived Markdown H1.

Example:

```json
{
  "date": "2026-10-11",
  "profiles": {
    "business": {
      "candidates": [
        "品牌A增长之后，真正难的是什么",
        "品牌A开出100家店，复制难在哪",
        "品牌A走出本地后，供应链先卡住了"
      ],
      "selected_title": "品牌A开出100家店，复制难在哪",
      "rationale": "公司名和具体事件更清楚，避免泛化标题，同时保留经营冲突。",
      "basis": ["account_fit", "specific_event", "30d_novelty", "evidence_strength"],
      "verified_views": null
    }
  }
}
```

Do not invent popularity or reading metrics. `verified_views` stays null until
a real backend/manual observation exists. Later feedback can be joined by
date/profile/title without rewriting the original decision rationale.

The ledger is editorial evidence only. A missing ledger must never cause a
second WeChat `draft/add` call or modification of an already-confirmed draft.
