# Reading performance feedback

Fallback for accounts whose WeChat Datacube endpoints are unavailable or return `48001 api unauthorized`.

Append only **verified** observations to `manual.jsonl` when a real reading figure is available. One JSON object per line:

```json
{"profile":"business","date":"2026-10-10","title":"Example title","views":123,"source":"WeChat backend screenshot/manual observation"}
```

If only a qualitative observation is known, keep `views` null and add a note. Never convert labels such as “better than usual” into an invented number.

```json
{"profile":"business","date":"2026-10-10","title":"Example title","views":null,"source":"manual observation","note":"relative performance only"}
```

The daily summarizer only computes numeric averages from verified integer `views`. It is advisory and should not change editorial direction from one or two samples.
