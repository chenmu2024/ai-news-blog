# Manual review ledger

Use this only when a workflow or editor explicitly requires human/manual investigation. The ledger is append-only and must not contain invented approvals.

Each line in `decisions.jsonl` is one JSON object:

```json
{"date":"2026-10-11","profile":"fashion","stage":"image","subject":"photo provenance for article X","decision":"approved","reviewer":"human/operator name or role","evidence":["source URL","licence page URL"],"note":"what was checked"}
```

Allowed stages: source, topic, fact, image, draft, retry, metrics.
Allowed decisions: approved, rejected, escalated, not_applicable.

A missing manual decision never becomes approval. A model-generated suggestion is not a human review. For draft/add unknown outcomes, the reviewer must inspect the durable journal and WeChat backend before any retry.
