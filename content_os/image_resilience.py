"""Validate and stage article images *before* contacting WeChat.

Works without paid APIs, cookies, browser sessions or CAPTCHA bypass.
Unlicensed/unrelated images are never silently substituted. Explicit alternate
images must be editorially verified as relevant and permitted for re-use.
The archive remains immutable after a successful draft receipt.
"""
from __future__ import annotations

from io import BytesIO
import ipaddress
import json
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
BACKUPS_RE = re.compile(r"<!--\s*IMAGE_BACKUPS\s*(\{[\s\S]*?\})\s*-->", re.S)
FASHION_RE = re.compile(r"<!--\s*FASHION_SOURCE\s*(\{[\s\S]*?\})\s*-->", re.S)
SUPPORTED_RIGHTS = {"owned", "permission", "pexels_license", "unsplash_license",
                    "commons_licensed", "cc0", "public_domain"}
MAX_BYTES = 14 * 1024 * 1024
MAX_PIXELS = 28_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
UA = "Mozilla/5.0 (compatible; ContentOSImagePreflight/1.0)"


def public_https(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme != "https" or not p.hostname or p.username or p.password:
            return False
        host = p.hostname.lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except (ValueError, TypeError):
        return False


def pexels_jpeg_variant(url: str) -> str | None:
    """Pexels may serve AVIF despite a .jpeg path; force its documented JPEG transform."""
    p = urlparse(url)
    if p.hostname != "images.pexels.com":
        return None
    query = dict(parse_qsl(p.query, keep_blank_values=False))
    if query.get("fm") == "jpg" and query.get("auto") is None:
        return None
    query.pop("auto", None)
    query.pop("cs", None)
    query["fm"] = "jpg"
    query.setdefault("w", "1200")
    return urlunparse(p._replace(query=urlencode(query)))


def _read_backups(markdown: str) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    specs = []
    for regex in (BACKUPS_RE, FASHION_RE):
        for match in regex.finditer(markdown):
            try:
                raw = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                raise ValueError("Image fallback metadata is invalid JSON") from exc
            if regex is BACKUPS_RE:
                if not isinstance(raw, dict) or not isinstance(raw.get("images", []), list):
                    raise ValueError("IMAGE_BACKUPS.images must be an array")
                specs.extend(raw.get("images", []))
            elif isinstance(raw, dict):
                specs.extend(raw.get("images", []))
    for entry in specs:
        if not isinstance(entry, dict):
            continue
        primary = entry.get("primary") or entry.get("image_url")
        if not isinstance(primary, str):
            continue
        alternatives = entry.get("alternatives", [])
        if not isinstance(alternatives, list):
            continue
        for candidate in alternatives:
            if not isinstance(candidate, dict):
                continue
            candidate_url = candidate.get("image_url") or candidate.get("url")
            source_page = candidate.get("source_page_url")
            verified = candidate.get("verified") is True
            subject_match = candidate.get("subject_match") is True
            rights = candidate.get("rights")
            if (isinstance(candidate_url, str) and public_https(candidate_url)
                    and isinstance(source_page, str) and public_https(source_page)
                    and verified and subject_match and rights in SUPPORTED_RIGHTS):
                mapping.setdefault(primary, []).append(candidate_url)
    return mapping


def _jpeg_from_response(response, requested: str) -> tuple[bytes, str, str]:
    response.raise_for_status()
    data = response.content
    if not data or len(data) > MAX_BYTES:
        raise ValueError("empty or oversized image")
    ct = response.headers.get("Content-Type", "").split(";")[0].lower()
    if not ct.startswith("image/"):
        raise ValueError("non-image Content-Type: " + ct)
    try:
        with Image.open(BytesIO(data)) as opened:
            if opened.format not in ("PNG", "JPEG", "WEBP", "AVIF"):
                raise ValueError("unsupported image format: " + str(opened.format))
            if opened.width < 160 or opened.height < 160:
                raise ValueError("image is too small")
            if opened.width * opened.height > MAX_PIXELS:
                raise ValueError("image pixel count too high")
            img = ImageOps.exif_transpose(opened)
            img.thumbnail((1200, 1200))
            if img.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", img.size, "white")
                bg.paste(img.convert("RGB"), mask=img.getchannel("A"))
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            output = BytesIO()
            img.save(output, format="JPEG", quality=82, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("image decoder rejected content: " + type(exc).__name__) from exc
    return output.getvalue(), "image/jpeg", ".jpg"


def _get_image(url: str, session=None) -> tuple[bytes, str, str]:
    if not public_https(url):
        raise ValueError("Only public HTTPS image sources are allowed")
    requester = session or requests
    headers = {"User-Agent": UA, "Accept": "image/jpeg,image/png,image/webp;q=0.8,*/*;q=0.1"}
    last = None
    for attempt in range(3):
        try:
            response = requester.get(url, timeout=22, headers=headers, allow_redirects=True)
            final_url = getattr(response, "url", url) or url
            if not public_https(final_url):
                raise ValueError("Image redirected to a non-public URL")
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                last = RuntimeError("transient HTTP " + str(response.status_code))
                time.sleep(attempt + 1)
                continue
            return _jpeg_from_response(response, url)
        except (requests.RequestException, ValueError, OSError) as exc:
            last = exc
            if attempt < 2 and isinstance(exc, (requests.ConnectionError, requests.Timeout)):
                time.sleep(attempt + 1)
                continue
            break
    raise RuntimeError("Image source unavailable: " + url + " (" +
                       type(last).__name__ + ")") from last


def prepare_images(markdown: str, profile: str, session=None) -> dict[str, tuple[bytes, str, str]]:
    """All-or-nothing staging; never upload anything to WeChat on preflight failure.

    Each original image URL is preserved for article rendering. An alternate
    is allowed only after editorial metadata explicitly validates rights and
    subject relevance; never substitute generic stock for a named person.
    """
    if profile not in {"wechat", "business", "zizhitongjian", "parenting",
                       "jingyun", "fashion"}:
        raise ValueError("Unknown image preflight profile")
    urls = list(dict.fromkeys(IMAGE_RE.findall(markdown)))
    if profile == "fashion" and len(urls) < 5:
        raise ValueError("Fashion requires at least five distinct real images")
    if not urls:
        return {}
    backups = _read_backups(markdown)
    result = {}
    for original in urls:
        candidates = [original]
        variant = pexels_jpeg_variant(original)
        if variant:
            candidates.append(variant)
        candidates += backups.get(original, [])
        tried = []
        for candidate in dict.fromkeys(candidates):
            try:
                result[original] = _get_image(candidate, session=session)
                if candidate != original:
                    print("[IMAGE_BACKUP] approved same-image or editorial alternate", original, "->", candidate)
                break
            except (ValueError, RuntimeError) as exc:
                tried.append(type(exc).__name__ + ": " + str(exc)[:160])
        if original not in result:
            raise RuntimeError("Preflight failed for image: " + original + " | " + "; ".join(tried))
    return result


def strip_image_backup_notes(markdown: str) -> str:
    """Production/source metadata cannot leak into the public WeChat article."""
    return BACKUPS_RE.sub("", markdown)
