"""Recover ONLY confirmed, already-created WeChat drafts by read-only draft/get.

No image upload, no draft/add, no draft/update, and no public send API.
The original write-ahead journal must include the exact uploaded image URLs,
a matching media_id, immutable archive hash and trusted PASS gate snapshots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from content_os.public_draft_contract import PROFILES, verify_and_record

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.weixin.qq.com/cgi-bin"
ENV = {
    "qiezhi": ("QIEZHI_WECHAT_APP_ID", "QIEZHI_WECHAT_APP_SECRET"),
    "wechat": ("WECHAT_APP_ID", "WECHAT_APP_SECRET"),
    "business": ("BUSINESS_WECHAT_APP_ID", "BUSINESS_WECHAT_APP_SECRET"),
    "zizhitongjian": ("TONGJIAN_WECHAT_APP_ID", "TONGJIAN_WECHAT_APP_SECRET"),
    "parenting": ("PARENTING_WECHAT_APP_ID", "PARENTING_WECHAT_APP_SECRET"),
    "jingyun": ("JINGYUN_WECHAT_APP_ID", "JINGYUN_WECHAT_APP_SECRET"),
    "fashion": ("FASHION_WECHAT_APP_ID", "FASHION_WECHAT_APP_SECRET"),
}

def read(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text("utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def candidate(root: Path, profile: str, day: str) -> tuple[dict | None, str]:
    if profile not in PROFILES:
        raise ValueError("Unknown account")
    archive = root / profile / "archive" / (day + ".md")
    journal = read(root / profile / "status" / "draft-attempts" / (day + ".json"))
    if journal.get("state") != "confirmed":
        return None, "skip_not_confirmed"
    if not archive.is_file():
        return None, "blocked_missing_archive"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    rel = f"{profile}/archive/{day}.md"
    title = next((x[2:].strip() for x in archive.read_text("utf-8").splitlines()
                  if x.startswith("# ")), "")
    if (journal.get("profile") != profile or journal.get("article_path") != rel or
        journal.get("article_sha256") != digest or journal.get("title") != title or
        not journal.get("draft_media_id") or not title):
        return None, "blocked_journal_archive_mismatch"
    existing = read(root / profile / "status" / "draft-readback" / (day + ".json"))
    if (existing.get("draft_get_verified") is True and
        existing.get("draft_media_id") == journal["draft_media_id"] and
        existing.get("article_sha256") == digest and
        existing.get("article_path") == rel and
        existing.get("article_date") == day and
        (existing.get("inline_image_count") or 0) >= (5 if profile=="fashion" else 1)):
        return None, "skip_already_readback_verified"
    required = {"quality-gate.json", "visual-gate.json"}
    if profile == "fashion":
        required.add("image-gate.json")
    if profile == "zizhitongjian":
        required.add("source-gate.json")
    snapshots = journal.get("passed_gates")
    if not isinstance(snapshots, dict) or set(snapshots) != required:
        return None, "blocked_missing_bound_gate_snapshot"
    for name in required:
        g = snapshots[name]
        if (not isinstance(g, dict) or g.get("status") != "PASS" or
            g.get("article_sha256") != digest or g.get("article_path") != rel):
            return None, "blocked_untrusted_gate_snapshot"
    urls = journal.get("expected_inline_urls")
    min_images = 5 if profile == "fashion" else 1
    if (not isinstance(urls, list) or len(urls) < min_images or
        not all(isinstance(u, str) and urlparse(u).scheme == "https" and
                urlparse(u).hostname == "mmbiz.qpic.cn" for u in urls)):
        return None, "blocked_missing_uploaded_image_fingerprints"
    return {"journal": journal, "archive": archive, "title": title, "urls": urls}, "eligible"


def recover_one(root: Path, profile: str, day: str, transport=None,
                credentials=None) -> dict:
    state, reason = candidate(root, profile, day)
    if state is None:
        return {"profile": profile, "result": reason}
    credentials = credentials or tuple(os.getenv(name, "") for name in ENV[profile])
    if not all(credentials):
        return {"profile": profile, "result": "missing_wechat_credentials"}
    # Lazy import ensures offline checks never need network packages.
    if transport is None:
        import requests
        transport = requests.request
    proxy = os.getenv("PROXY_URL", "").strip()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    def request(method, url, **kwargs):
        result = transport(method, url, proxies=proxies, **kwargs)
        result.raise_for_status()
        return result
    try:
        res = request("GET", API + "/token", params={
            "grant_type": "client_credential",
            "appid": credentials[0], "secret": credentials[1],
        }, timeout=30)
        token = res.json().get("access_token")
        if not isinstance(token, str) or not token:
            return {"profile": profile, "result": "wechat_token_rejected"}
        # Only an HTML expectation made of the journalled, previously uploaded
        # image URLs. Verification compares the saved draft to their qpic paths.
        expected = "<section>" + "".join(
            f'<img src="{u}" />' for u in state["urls"]) + "</section>"
        verify_and_record(profile, state["archive"], state["title"],
                          state["journal"]["draft_media_id"], expected,
                          token, request, API)
        return {"profile": profile, "result": "recovered_verified_existing_draft",
                "image_count": len(state["urls"])}
    except Exception as exc:
        # Never log request URLs: /token includes the app secret in parameters.
        return {"profile": profile, "result": "readback_failed",
                "error_class": type(exc).__name__}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--date", default=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat())
    args = p.parse_args()
    if args.root.resolve() != Path.cwd().resolve():
        raise RuntimeError("Recovery must run from checked-out repository root")
    results = [recover_one(args.root, item, args.date) for item in PROFILES]
    print(json.dumps({"date": args.date, "results": results}, ensure_ascii=False))
    # Per-profile errors are safe, recoverable states; health audit marks partial.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
