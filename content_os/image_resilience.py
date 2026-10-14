"""Validate and stage article images *before* contacting WeChat.

Works without paid APIs, cookies, browser sessions or CAPTCHA bypass.
Unlicensed/unrelated images are never silently substituted. Contextual
stock-photo alternatives are permitted for the four illustration-led profiles;
celebrity, product and business evidence photos keep strict subject matching.
The archive remains immutable after a successful draft receipt.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import hashlib
import os
import ipaddress
import json
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from PIL import Image, ImageOps, UnidentifiedImageError
try:
    from content_os.ai_scene_policy import asset_file as trusted_ai_scene_asset
except ImportError:
    from ai_scene_policy import asset_file as trusted_ai_scene_asset

IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
HTML_IMAGE_RE = re.compile(r"""<img\b[^>]*\bsrc\s*=\s*["']https?://[^"']+["']""", re.I)
BACKUPS_RE = re.compile(r"<!--\s*IMAGE_BACKUPS\s*(\{[\s\S]*?\})\s*-->", re.S)
AI_SCENE_RE = re.compile(r"<!--\s*AI_SCENE\s*(\{[\s\S]*?\})\s*-->", re.S)
FASHION_RE = re.compile(r"<!--\s*FASHION_SOURCE\s*(\{[\s\S]*?\})\s*-->", re.S)
SUPPORTED_RIGHTS = {"owned", "permission", "pexels_license", "unsplash_license",
                    "pixabay_license", "commons_licensed", "cc0", "public_domain"}
# Informational/lifestyle channels may use Pexels/Unsplash-like *illustration*
# that matches the paragraph scene rather than the very same pictured person.
SCENE_IMAGE_PROFILES = frozenset({"qiezhi", "zizhitongjian", "parenting", "jingyun"})
STRICT_IMAGE_PROFILES = frozenset({"wechat", "business", "fashion"})
ALL_PROFILES = SCENE_IMAGE_PROFILES | STRICT_IMAGE_PROFILES
MAX_BYTES = 14 * 1024 * 1024
MAX_PIXELS = 28_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
UA = "ContentOSWeChatDraft/1.0 (https://github.com/chenmu2024/ai-news-blog; support: https://github.com/chenmu2024/ai-news-blog/issues)"


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


def _read_backups(markdown: str, profile: str) -> dict[str, list[str]]:
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
            # Scene-only matches are accepted for four illustrative channels,
            # never for documentary/celebrity/product/business evidence.
            scene_match = candidate.get("scene_match") is True
            relevant = subject_match or (profile in SCENE_IMAGE_PROFILES and scene_match)
            rights = candidate.get("rights")
            if (isinstance(candidate_url, str) and public_https(candidate_url)
                    and isinstance(source_page, str) and public_https(source_page)
                    and verified and relevant and rights in SUPPORTED_RIGHTS):
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
        raise ValueError("Only HTTPS image identities are allowed")
    # Private repository assets cannot be anonymously GET'd from GitHub Raw.
    # Read the actual checked-out binary file; it is subsequently converted,
    # staged and POSTed to WeChat, whose returned image URL is publicly readable.
    local_asset = trusted_ai_scene_asset(url)
    if local_asset is not None:
        try:
            payload = local_asset.read_bytes()
            mime = ("image/webp" if local_asset.suffix.lower() == ".webp" else
                    "image/png" if local_asset.suffix.lower() == ".png" else "image/jpeg")
            class _LocalVerifiedResponse:
                content = payload
                headers = {"Content-Type": mime}
                def raise_for_status(self):
                    return None
            return _jpeg_from_response(_LocalVerifiedResponse(), url)
        except (OSError, ValueError) as exc:
            raise RuntimeError("Private AI scene image not readable or decodable: " + str(local_asset)) from exc
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
    status = getattr(getattr(last, "response", None), "status_code", None)
    raise RuntimeError("Image source unavailable: " + url + " (" +
                       type(last).__name__ + ("/HTTP" + str(status) if status else "") + ")") from last


def save_prepared_cache(markdown: str, profile: str,
                        prepared: dict[str, tuple[bytes, str, str]],
                        folder: Path) -> None:
    """Store only validated JPEG bytes in ephemeral runner storage, never in git."""
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": 1, "profile": profile,
                "article_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                "images": {}}
    for url, (data, content_type, extension) in prepared.items():
        if content_type != "image/jpeg" or extension != ".jpg" or not data.startswith(bytes.fromhex("ffd8")):
            raise ValueError("Only validated JPEG stage data can be cached")
        name = hashlib.sha256(url.encode("utf-8")).hexdigest() + ".jpg"
        (folder / name).write_bytes(data)
        manifest["images"][url] = {"file": name, "sha256": hashlib.sha256(data).hexdigest()}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")


def load_prepared_cache(markdown: str, profile: str, folder: Path,
                        urls: list[str]) -> dict[str, tuple[bytes, str, str]]:
    """Fail closed on missing/corrupt cache; no second network GET after preflight."""
    try:
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        expected = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        if (manifest.get("schema") != 1 or manifest.get("profile") != profile or
                manifest.get("article_sha256") != expected or
                set(manifest.get("images", {})) != set(urls)):
            raise ValueError("Staged image manifest differs from current archive")
        result = {}
        for url in urls:
            record = manifest["images"][url]
            name = hashlib.sha256(url.encode("utf-8")).hexdigest() + ".jpg"
            if record.get("file") != name:
                raise ValueError("Unexpected image stage filename")
            data = (folder / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != record.get("sha256"):
                raise ValueError("Staged JPEG checksum mismatch")
            with Image.open(BytesIO(data)) as image:
                if image.format != "JPEG" or min(image.size) < 160:
                    raise ValueError("Invalid cached JPEG bytes")
            result[url] = (data, "image/jpeg", ".jpg")
        print("[IMAGE_STAGE] reused validated preflight JPEGs:", len(result))
        return result
    except (OSError, ValueError, KeyError, TypeError, UnidentifiedImageError) as exc:
        raise RuntimeError("Staged image cache unavailable or tampered; refuse WeChat upload") from exc


def prepare_images(markdown: str, profile: str, session=None) -> dict[str, tuple[bytes, str, str]]:
    """All-or-nothing staging; never upload anything to WeChat on preflight failure.

    Each original image URL is preserved for article rendering. Alternatives
    require editorial evidence for rights and relevance. qiezhi/zizhitongjian/
    parenting/jingyun may use scene-matched free stock, only as illustration;
    celebrity, named-person, product and business evidence remain strict.
    """
    if profile not in ALL_PROFILES:
        raise ValueError("Unknown image preflight profile")
    if HTML_IMAGE_RE.search(markdown):
        raise ValueError("External HTML <img> must be Markdown image syntax for safe WeChat upload")
    urls = list(dict.fromkeys(IMAGE_RE.findall(markdown)))
    if profile == "fashion" and len(urls) < 5:
        raise ValueError("Fashion requires at least five distinct real images")
    if not urls:
        return {}
    if os.environ.get("CONTENT_OS_IMAGE_CACHE_READ") == "1":
        folder = os.environ.get("CONTENT_OS_IMAGE_CACHE_DIR")
        if not folder:
            raise RuntimeError("Image stage reuse requested without cache directory")
        return load_prepared_cache(markdown, profile, Path(folder), urls)
    backups = _read_backups(markdown, profile)
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


COMIC_PACKAGE_RE = re.compile(r"<!--\\s*COMIC_PACKAGE\\s*(\\{[\\s\\S]*?\\})\\s*-->", re.S)\n\ndef strip_image_backup_notes(markdown: str, profile: str | None = None) -> str:
    """Remove production metadata and A-F figure captions from public copy."""
    from content_os.public_draft_contract import strip_figure_captions
    public = COMIC_PACKAGE_RE.sub("", AI_SCENE_RE.sub("", BACKUPS_RE.sub("", markdown)))
    return strip_figure_captions(public, profile) if profile else public
