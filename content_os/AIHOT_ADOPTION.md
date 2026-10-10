# AIHOT-inspired editorial intelligence: adoption and release gates

This module is **advisory only**. It does not draft or publish to WeChat, and must never trigger archive push or draft/add. Existing seven-account SOURCE_POLICY/STYLE, original texts, media/source gates and idempotency remain authoritative.

## Sources
`source_registry.json` specifies independent discovery sources and fallback sites for each account. Some links are homepages rather than structured feeds: **connectors must test access, robots, date, terms and extraction before promoting them to active collectors**. These are configuration candidates, not evidence that a feed was fetched. Primary failure -> fallback -> recorded insufficient_evidence; never bypass logins/captcha or pay for sources. Official text and image permissions are separate hard gates.

## Input and output
`python content_os/editorial_intelligence.py --input /tmp/candidates.json --history /tmp/history.json --output /tmp/editorial-ranked.json`

Input JSON array: {profile,title,url,source,published_at,summary,evidence_level,heat_verified,relevance,title_hook,event_id,title_candidates,recent_views,baseline_views,primary_text_verified}. History JSON maps profile to prior titles. Empty/unknown metrics must remain null. Score weights are experimental, **not evidence of WeChat traffic or independently corroborated facts**. Title candidates require independent human/agent fact and originality checks.

Output contains profile-specific ranked clusters, flags, independent sources and metrics. Sequence similarity is an inexpensive candidate-level duplicate heuristic, not a semantic event classifier. Never merge distinct legal, medical, political, or historical facts solely on string similarity. Event_id must be externally verified, not inferred from shared keywords.

## Editorial tracking record
For each candidate retain discovery timestamp, URL, original publication timestamp/time zone, credibility tier, event_id, manual decision and rationale, exclusion/duplication result, three non-copying title candidates, chosen title, archive SHA256, gates, attempt journal and draft receipt. When available, record read count with observation window and source (not a guessed value). Feedback should compare like-for-like baseline and avoid causal claims from 1-2 samples.

## Mandatory lifecycle
source discovery -> fallback decision -> date verification -> event duplicate review -> separate account score -> editorial decision -> original text/fact gate -> writing -> image URL license and decoded bytes -> readiness/quality/visual/source/image gates -> immutable archive -> existing GitHub Actions -> journal attempted/confirmed -> SHA+title+today+gates+draft receipt reconciliation. Unknown status after a draft/add timeout is **manual investigation**, not retry. Only pre-draft transient tasks may retry with bounded backoff; all seven accounts execute independently.

## Existing invariants
- A qiezhi: exact citations from official Mao Selected Works volumes 1–4; never skip due to trending-source shortage.
- B wechat: headline starts with 一家; real project claims; use relevant real screenshots/graphs instead of arbitrary branding.
- C business: prioritize company name and verifiable financial evidence.
- D zizhitongjian: cross-check source passages; describe fallback accurately.
- E parenting: prioritize school and family realities; avoid medical inventions or anxiety-bait.
- F jingyun: avoid invented personal narrative and inflammatory stereotypes.
- G fashion: celebrity-led; at least five distinct confirmed accessible authentic photos with provenance and reuse rights.
- Every account must pass its existing visual/image constraints; no invented source popularity, reads, rankings or permissions.
- Automation schedule remains 08:20 production and 11:20 missing-only review; never auto mass-send.

## Release validation
`python -m unittest content_os.test_editorial_intelligence`
`python -m compileall -q content_os`
Run existing CI reliability regression and `publish_readiness.py` on an unsubmitted staging article per profile. A real end-to-end pass requires seven verified same-day official WeChat draft receipts, not merely seven green quality gates. Keep this advisory module outside the publish workflow until its trial data and tests are verified.

## Daily advisory artifact (automated)
The existing free-topic-discovery workflow now runs `content_os/build_editorial_shortlist.py` after collecting its same-day source index and commits `content_os/editorial-intelligence/YYYY-MM-DD.json`. Before selecting an article, check **today's** file and its `flags`, then consult original articles and near-30-day archive. Do not treat `score` as established readership or `heat_verified=false` as popularity. Old or missing daily artifact means insufficient evidence, not a pass. This workflow does not generate three titles by itself, access WeChat statistics, or draft any article; those remain editorial/production-stage responsibilities. If the collector fails, consult `topic-intelligence/latest.json` and log failure; never reuse yesterday's shortlist as today.

## Source health artifact
Before research selection, read `content_os/source-health/latest.json` and require its date to match the current Asia/Shanghai day. A source marked unreachable/http_error is not proof the publisher is down globally; it only means the GitHub runner could not reach that URL at audit time. Prefer a reachable primary source; if all primaries fail, use a reachable fallback and record the downgrade. Reachability never substitutes for freshness, factual verification, copyright/reuse rights, or original-text verification. If both primary and fallback are unavailable, continue the other accounts independently and record insufficient_evidence rather than inventing facts or retrying indefinitely.
