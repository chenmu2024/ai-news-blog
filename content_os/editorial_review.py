"""Offline evidence contract for new editorial work, never an AI-writing detector.

Validates that a producer recorded two editorial passes on these exact bytes.
It cannot judge taste, verify a URL's claims or substitute for reading sources.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ACTIVATION = "2026-10-14"
CHECKS = {
    "qiezhi": ("original_context", "single_real_problem"),
    "wechat": ("paid_task", "cost_or_tradeoff", "evidence_scope"),
    "business": ("eligibility", "official_entry", "steps_and_limits"),
    "parenting": ("eligibility", "amount_example", "official_entry"),
    "zizhitongjian": ("event_sequence", "conflict_and_consequence", "historian_comment"),
    "jingyun": ("observable_detail", "choice_and_cost", "ending_without_lecture"),
    "fashion": (),
}


def _text(value, minimum=8):
    return isinstance(value, str) and len(value.strip()) >= minimum


def _visible(markdown):
    return re.sub(r"<!--.*?-->|!\[[^\]]*\]\([^)]+\)", "", markdown, flags=re.S)


def _anchor(value, body):
    return _text(value) and re.sub(r"\s+", "", value) in re.sub(r"\s+", "", body)


def review_path(root, profile, day):
    return root / "content_os/editorial-reviews" / profile / (day + ".json")


def policy_hash(root, profile):
    paths = ["content_os/PRODUCTION_BRIEF.md", "content_os/EDITORIAL_VOICE.md",
             "content_os/editorial-feedback.json", f"{profile}/STYLE.md"]
    return hashlib.sha256(b"\0".join((root / p).read_text("utf-8").encode("utf-8") for p in paths)).hexdigest()


def recent_archives(root, profile, day):
    target = date.fromisoformat(day)
    return sorted((p for p in (root / profile / "archive").glob("????-??-??.md")
                   if 0 < (target - date.fromisoformat(p.stem)).days <= 30), reverse=True)[:3]


def check(root: Path, profile: str, day: str, markdown: str) -> dict:
    if profile not in CHECKS or date.fromisoformat(day).isoformat() != day:
        raise ValueError("Invalid editorial profile/date")
    if day < ACTIVATION:
        return {"status": "NOT_REQUIRED", "errors": []}
    errors = []
    try:
        rec = json.loads(review_path(root, profile, day).read_text("utf-8"))
        if not isinstance(rec, dict):
            raise ValueError("not an object")
        feedback = json.loads((root / "content_os/editorial-feedback.json").read_text("utf-8"))
        if (not isinstance(feedback, dict) or not isinstance(feedback.get("items"), list)
                or any(not isinstance(x, dict) or not isinstance(x.get("id"), str)
                       or not isinstance(x.get("profiles"), list) for x in feedback["items"])):
            raise ValueError("invalid feedback")
        expected_policy = policy_hash(root, profile)
    except (OSError, ValueError, UnicodeError):
        return {"status": "FAIL", "errors": ["editorial_review_or_policy_missing_or_invalid"]}
    if (rec.get("schema_version") != 1 or rec.get("profile") != profile
            or rec.get("date") != day or rec.get("decision") != "approve"):
        errors.append("editorial_review_not_approved_for_profile_and_date")
    if rec.get("article_sha256") != hashlib.sha256(markdown.encode("utf-8")).hexdigest():
        errors.append("editorial_review_stale_article")
    if rec.get("policy_sha256") != expected_policy:
        errors.append("editorial_review_stale_policy")
    for field in ("reader", "question", "new_information", "topic_key"):
        if not _text(rec.get(field)):
            errors.append("editorial_missing_" + field)
    evidence = rec.get("evidence")
    body = _visible(markdown)
    if not isinstance(evidence, list) or not evidence:
        errors.append("editorial_source_evidence_missing")
    else:
        for item in evidence:
            if not isinstance(item, dict):
                errors.append("editorial_source_evidence_invalid")
                continue
            try:
                url = urlparse(str(item.get("url") or ""))
                valid_url = url.scheme == "https" and bool(url.hostname)
            except ValueError:
                valid_url = False
            observation = profile == "jingyun" and item.get("kind") == "observation" and not item.get("url")
            if ((not observation and not valid_url) or not _text(item.get("claim"))
                    or not _anchor(item.get("article_excerpt"), body)):
                errors.append("editorial_source_evidence_invalid")
    alternatives = rec.get("rejected_topics")
    if (not isinstance(alternatives, list) or len(alternatives) < 2
            or any(not isinstance(x, dict) or not _text(x.get("question"))
                   or not _text(x.get("reason")) for x in alternatives)):
        errors.append("editorial_needs_two_rejected_topic_angles_not_title_variants")
    history = rec.get("history")
    if not isinstance(history, list):
        history = []
    compared = {x["path"]: x.get("difference") for x in history
                if isinstance(x, dict) and isinstance(x.get("path"), str)}
    for path in recent_archives(root, profile, day):
        if not _text(compared.get(path.relative_to(root).as_posix())):
            errors.append("editorial_recent_history_comparison_missing")
    checks = rec.get("profile_checks")
    if not isinstance(checks, dict):
        checks = {}
    for name in CHECKS[profile]:
        if not _anchor(checks.get(name), body):
            errors.append("editorial_profile_evidence_missing:" + name)
    if profile == "fashion":
        photos = checks.get("photo_analysis")
        urls = re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", markdown)
        if not isinstance(photos, list):
            photos = []
        mapped = {p["image_url"]: p.get("article_excerpt") for p in photos
                  if isinstance(p, dict) and isinstance(p.get("image_url"), str)}
        if len(set(urls)) < 5 or set(mapped) != set(urls):
            errors.append("editorial_fashion_each_photo_needs_analysis")
        if (any(not _anchor(mapped.get(url), body) for url in urls)
                or len({str(x) for x in mapped.values()}) != len(mapped)):
            errors.append("editorial_fashion_analysis_missing_or_reused")
    for role in ("reader_review", "fact_review"):
        review = rec.get(role)
        if not isinstance(review, dict):
            review = {}
        if (not _text(review.get("finding")) or not _text(review.get("change"))
                or not _anchor(review.get("final_excerpt"), body)
                or review.get("unresolved") != []):
            errors.append("editorial_incomplete_" + role)
    applied = rec.get("feedback_applied")
    if not isinstance(applied, list):
        applied = []
    applied = {x["id"]: x.get("change") for x in applied
               if isinstance(x, dict) and isinstance(x.get("id"), str)}
    for item in feedback.get("items", []):
        if item.get("active") is True and profile in item.get("profiles", []):
            if not _text(applied.get(item["id"])):
                errors.append("editorial_feedback_not_addressed:" + item["id"])
    # Exact topic keys supplement, never replace, the producer's semantic review.
    others = [profile] + (["parenting"] if profile == "business" else
                          ["business"] if profile == "parenting" else [])
    for other in others:
        for path in (root / "content_os/editorial-reviews" / other).glob("????-??-??.json"):
            old_day = date.fromisoformat(path.stem)
            distance = (date.fromisoformat(day) - old_day).days
            if not (0 < distance <= 30 or (distance == 0 and other != profile)):
                continue
            try:
                old = json.loads(path.read_text("utf-8"))
                if (isinstance(old, dict) and old.get("decision") == "approve"
                        and old.get("topic_key") == rec.get("topic_key")):
                    errors.append("editorial_repeated_topic_key")
            except (OSError, ValueError):
                errors.append("editorial_history_review_unreadable")
    return {"status": "FAIL" if errors else "PASS", "errors": sorted(set(errors)),
            "note": "Evidence completeness only; not a score of writing quality or verified facts."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=CHECKS)
    parser.add_argument("--date", required=True)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = check(args.root, args.profile, args.date, args.article.read_bytes().decode("utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["status"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
