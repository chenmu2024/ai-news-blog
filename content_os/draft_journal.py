"""Write-ahead, per-day WeChat draft/add journal (GitHub Contents API).

This is intentionally fail-closed. Recording intent happens IMMEDIATELY before
/draft/add; a lost HTTP response cannot be interpreted as permission to retry.
Confirmed media_id is stored on GitHub independently of later git status sync.
No broadcast/publish API is involved.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


def journal_path(profile: str, article: Path) -> str:
    if article.parent.name != "archive" or article.parent.parent.name != profile:
        raise ValueError("Invalid archive path for journal")
    return profile + "/status/draft-attempts/" + article.stem + ".json"


def _environment() -> tuple[str, str, str]:
    token = os.getenv("CONTENT_OS_GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if not token or "/" not in repo or not run_id:
        raise RuntimeError("No durable GitHub journal access. Refuse WeChat draft/add.")
    return token, repo, run_id


def _endpoint(repo: str, path: str) -> str:
    return "https://api.github.com/repos/" + repo + "/contents/" + quote(path, safe="/")


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict | None:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        url, data=data, method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        if method == "GET" and exc.code == 404:
            return None
        raise


def _get(token: str, repo: str, path: str) -> tuple[dict | None, str | None]:
    result = _request("GET", _endpoint(repo, path), token)
    if not result:
        return None, None
    raw = base64.b64decode(result["content"]).decode("utf-8")
    return json.loads(raw), result["sha"]


def _put(token: str, repo: str, path: str, value: dict, sha: str | None) -> None:
    data = {"message": "safety: store WeChat draft/add write-ahead journal",
            "content": base64.b64encode((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii"),
            "branch": "main"}
    if sha:
        data["sha"] = sha
    _request("PUT", _endpoint(repo, path), token, data)


def gate_snapshot(profile: str, article: Path) -> dict | None:
    """Capture exact PASS artifacts so a confirmed draft can recover after sync crash.

    Missing/stale reports never become invented PASS values. The normal draft
    creation still uses its own gates; snapshots only authorize later recovery.
    """
    files = ["quality-gate.json", "visual-gate.json"]
    if profile == "fashion":
        files.append("image-gate.json")
    if profile == "zizhitongjian":
        files.append("source-gate.json")
    expected = hashlib.sha256(article.read_bytes()).hexdigest()
    checked = {}
    for name in files:
        try:
            report = json.loads((Path(profile) / "status" / name).read_text("utf-8"))
        except (OSError, ValueError):
            return None
        if (report.get("status") != "PASS" or
                report.get("article_sha256") != expected or
                report.get("article_path") != article.as_posix()):
            return None
        checked[name] = report
    return checked


def reserve(profile: str, article: Path, title: str, public_body_html: str | None = None) -> None:
    """Record the public WeChat image URLs before its non-idempotent draft/add.

    The already-uploaded image URLs let a later health audit verify the very
    same saved draft using only draft/get. No image upload or second add needed.
    """
    try:
        from content_os.editorial_review import check as editorial_check
    except ImportError:
        from editorial_review import check as editorial_check
    review = editorial_check(article.resolve().parents[2], profile, article.stem,
                             article.read_bytes().decode("utf-8"))
    if review["status"] == "FAIL":
        raise RuntimeError("Editorial review failed; refuse draft/add: " + "; ".join(review["errors"]))
    from content_os.public_draft_contract import image_sources
    from urllib.parse import urlparse
    urls = image_sources(public_body_html or "")
    if article.stem >= "2026-10-13":
        minimum = 5 if profile == "fashion" else 1
        if len(urls) < minimum:
            raise RuntimeError("Cannot reserve new draft without required inline WeChat images")
        for image_url in urls:
            parsed = urlparse(image_url)
            if parsed.scheme not in ("http", "https") or parsed.hostname != "mmbiz.qpic.cn":
                raise RuntimeError("Non-WeChat image URL in prepared draft body")
    token, repo, run_id = _environment()
    path = journal_path(profile, article)
    existing, _ = _get(token, repo, path)
    if existing:
        raise RuntimeError("Draft/add already attempted for this date; reconcile "
                           "journal/media_id before any new WeChat upload: " + path)
    intent = {
        "state": "attempted",
        "profile": profile,
        "article_path": article.as_posix(),
        "article_sha256": hashlib.sha256(article.read_bytes()).hexdigest(),
        "title": title,
        "run_id": run_id,
        "expected_inline_urls": urls,
    }
    passed_gates = gate_snapshot(profile, article)
    if article.stem >= "2026-10-11" and passed_gates is None:
        raise RuntimeError(
            "No SHA/path-bound PASS gate snapshot; refuse WeChat draft/add "
            "before write-ahead journal creation."
        )
    if passed_gates is not None:
        intent["passed_gates"] = passed_gates
    for attempt in range(5):
        try:
            _put(token, repo, path, intent, None)
            break
        except HTTPError as exc:
            if exc.code not in (409, 422, 429, 500, 502, 503, 504) or attempt == 4:
                raise
            # Concurrent journal writes for seven independent accounts may
            # race the main branch. A conflicting SAME-DAY intent must stop.
            previous, _ = _get(token, repo, path)
            if previous:
                raise RuntimeError("Another draft/add attempt already exists for " + path)
            time.sleep(1 + attempt)
    print("[DRAFT_JOURNAL] durable attempted reservation:", path)


def confirm(profile: str, article: Path, media_id: str) -> None:
    if not media_id:
        raise ValueError("Cannot confirm empty WeChat media_id")
    token, repo, run_id = _environment()
    path = journal_path(profile, article)
    for attempt in range(3):
        existing, sha = _get(token, repo, path)
        if not existing or existing.get("run_id") != run_id:
            raise RuntimeError("Missing or conflicting durable draft reservation")
        if existing.get("article_sha256") != hashlib.sha256(article.read_bytes()).hexdigest():
            raise RuntimeError("Archive modified during draft/add")
        if existing.get("state") == "confirmed":
            if existing.get("draft_media_id") != media_id:
                raise RuntimeError("Confirmed WeChat media_id conflict")
            return
        confirmed = dict(existing, state="confirmed", draft_media_id=media_id)
        try:
            _put(token, repo, path, confirmed, sha)
            print("[DRAFT_JOURNAL] stored confirmed WeChat media_id")
            return
        except HTTPError as exc:
            if exc.code != 409 or attempt == 2:
                raise


def locate(profile: str, article: Path, status_dir: Path | None = None) -> dict | None:
    if status_dir is None:
        file = Path(profile) / "status" / "draft-attempts" / (article.stem + ".json")
    else:
        file = status_dir / "draft-attempts" / (article.stem + ".json")
    try:
        value = json.loads(file.read_text("utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None
