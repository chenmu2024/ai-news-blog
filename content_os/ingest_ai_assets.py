"""Materialize genuinely generated AI image binaries from UTF-8 staging records.

The existing content-os-inbox-promote workflow runs this BEFORE evaluating
new candidates. GitHub Contents API only writes UTF-8; staging a base64 JSON
record is safe because the bot decodes and commits verified binary bytes.

No image is synthesized here. Fake or unverifiable records fail closed per
image; other account staging records continue.
"""
from __future__ import annotations
import argparse
import base64
import binascii
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
INBOX = Path("content_os/asset-staging")
OUT = Path("content_os/assets/ai-scenes")
PROFILES = {"qiezhi", "wechat", "business", "zizhitongjian", "parenting", "jingyun"}
IMAGE_TYPES = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
MAX_BYTES = 14 * 1024 * 1024

def ingest(root: Path) -> dict:
    root = root.resolve()
    work = root / INBOX
    ingested, already, failed = [], [], []
    if not work.exists():
        return {"ingested": [], "already": [], "failed": []}
    for input_path in sorted(work.rglob("*.json")):
        rel = input_path.relative_to(work)
        try:
            if len(rel.parts) != 3:
                raise ValueError("expected profile/day/name.ext.json")
            profile, day, name = rel.parts
            if profile not in PROFILES:
                raise ValueError("invalid profile")
            if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day):
                raise ValueError("invalid date")
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{1,110}\.(?:webp|png|jpe?g)\.json", name):
                raise ValueError("invalid filename")
            filename = name[:-5]
            raw = json.loads(input_path.read_text("utf-8"))
            if not isinstance(raw, dict) or raw.get("profile") != profile or raw.get("article_date") != day:
                raise ValueError("metadata profile/date mismatch")
            if raw.get("generator") not in {"openai_image_gen", "local_ai_image_model", "other_verified_ai_generator"}:
                raise ValueError("model identity not recorded")
            if not str(raw.get("generation_id") or "").strip():
                raise ValueError("real generation ID required")
            if (raw.get("synthetic") is not True or raw.get("scene_role") != "illustration" or
                    raw.get("rights") != "ai_created_owned"):
                raise ValueError("synthetic ownership attestation required")
            if len(str(raw.get("scene_description") or "").strip()) < 12:
                raise ValueError("scene description missing")
            encoded = raw.get("bytes_b64")
            if not isinstance(encoded, str) or len(encoded) > 19 * 1024 * 1024:
                raise ValueError("missing or oversized encoded image")
            data = base64.b64decode(encoded, validate=True)
            if not 0 < len(data) <= MAX_BYTES:
                raise ValueError("empty or oversized image")
            digest = hashlib.sha256(data).hexdigest()
            if raw.get("sha256") != digest:
                raise ValueError("SHA256 mismatch")
            with Image.open(BytesIO(data)) as img:
                if img.format != IMAGE_TYPES[Path(filename).suffix.lower()]:
                    raise ValueError("format/extension mismatch")
                if min(img.size) < 240 or img.width * img.height > 28_000_000:
                    raise ValueError("image size invalid")
                img.verify()
            asset = root / OUT / profile / day / filename
            if asset.exists():
                if asset.read_bytes() != data:
                    raise ValueError("asset exists with different bytes")
                already.append(str(asset.relative_to(root)))
            else:
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_bytes(data)
                ingested.append(str(asset.relative_to(root)))
            input_path.unlink()  # delete UTF-8 staging after binary is verified
        except (ValueError, OSError, KeyError, TypeError, UnidentifiedImageError,
                binascii.Error) as exc:
            failed.append({"path": str(rel), "error": str(exc)[:240]})
    return {"ingested": ingested, "already": already, "failed": failed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args()
    result = ingest(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    for f in result["failed"]:
        print("::warning::AI asset rejected:", f["path"], f["error"])
    # A bad asset for one account does not block other profiles.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
