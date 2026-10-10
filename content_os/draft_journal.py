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


def reserve(profile: str, article: Path, title: str) -> None:
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
    }
    _put(token, repo, path, intent, None)
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
