"""Fail-closed comic strip binary audit; never substitutes for human visual review.

Only new A–F articles (2026-10-15 onward). Checks source image bytes,
decode, dimensions and near-identical repeated strip renders before upload.
Generative provenance, aesthetics, legible Chinese and continuity require
separate human/visual inspection and the existing editorial attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

try:
    from content_os.comic_gate import required, check, MARKER, BASE
except ImportError:
    from comic_gate import required, check, MARKER, BASE


def _dhash(image: Image.Image) -> int:
    # Across complete strips this catches only extremely similar image pixels.
    # No style or storytelling inference is made from a perceptual checksum.
    gray = ImageOps.grayscale(image).resize((9, 8), Image.Resampling.LANCZOS)
    px = list(gray.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | int(px[y * 9 + x] > px[y * 9 + x + 1])
    return bits


def audit(profile: str, day: str, markdown: str, root: Path, *, preview: bool = False) -> list[str]:
    """Only an explicitly requested preview may skip *approval attestation*.

    Every publishing path uses preview=False. PREVIEW_PASS is never a publish
    approval or a substitute for Humanizer, editorial or user consent.
    """
    if not required(profile, day):
        return []
    errors = check(profile, day, markdown, root=root, verify_files=True)
    if preview:
        # Do not bypass source/structural/image/hash checks. Editorial/approval
        # attestation can be supplied only after the user sees the finished art.
        ignored = {"comic_user_approval_not_recorded_for_exact_candidate",
                   "comic_user_approved_body_hash_mismatch",
                   "comic_editorial_and_visual_attestation_incomplete"}
        errors = [e for e in errors if e not in ignored]
    # Structural errors invalidate image paths, so never guess paths on failure.
    if errors:
        return errors
    package = json.loads(MARKER.search(markdown).group(1))
    seen: list[tuple[int, int]] = []
    for i, item in enumerate(package["images"], start=1):
        url = item["url"]
        relative = url[len(BASE):]
        path = (root / relative).resolve()
        try:
            data = path.read_bytes()
            if not (20_000 <= len(data) <= 14 * 1024 * 1024):
                errors.append(f"comic_strip_{i}_binary_size_outside_bounds")
                continue
            with Image.open(io.BytesIO(data)) as raw:
                raw.verify()
            with Image.open(io.BytesIO(data)) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
                width, height = image.size
                if width < 600 or height < 500 or height > 20000:
                    errors.append(f"comic_strip_{i}_unreadable_mobile_dimensions")
                    continue
                if height / width < 0.70 or width > 2000:
                    errors.append(f"comic_strip_{i}_unexpected_comic_strip_aspect")
                current = _dhash(image)
            for prev_index, previous in seen:
                if (current ^ previous).bit_count() <= 3:
                    errors.append(f"comic_strip_{i}_near_duplicate_of_{prev_index}")
                    break
            seen.append((i, current))
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            errors.append(f"comic_strip_{i}_invalid_or_undecodable_image_bytes")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--article", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--preview", action="store_true",
                    help="Review-only; approval and editorial attestation remain pending. NEVER publish.")
    args = ap.parse_args()
    try:
        from content_os.multi_draft import get_article_identity
    except ImportError:
        from multi_draft import get_article_identity
    day, _ = get_article_identity(args.article, args.profile)
    failures = audit(args.profile, day, args.article.read_text("utf-8"), args.root,
                     preview=args.preview)
    print(json.dumps({"status": "FAIL" if failures else
                      ("PREVIEW_PASS_ONLY" if args.preview else "PASS"),
                      "publish_allowed": False if args.preview else not bool(failures),
                      "profile": args.profile, "article_date": day,
                      "errors": failures,
                      "note": "Binary and structural checks only; actual manual visual review remains required."},
                     ensure_ascii=False))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
