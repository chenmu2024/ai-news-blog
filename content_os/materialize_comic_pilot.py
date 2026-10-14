"""One-time verified materialization of 2026-10-14 two-account comic pilot assets.

Only copies original, human-reviewed JPEG bytes from a fixed archive. No WeChat
requests and no article/archive mutations.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import zipfile
from PIL import Image
from io import BytesIO

ROOT=Path(__file__).resolve().parents[1]
DAY="2026-10-14"
ZIP=ROOT/"content_os/asset-source/comic-pilot-20261014.zip"
PREFIX=ROOT/"content_os/assets/ai-scenes"
ALLOWED={"jingyun","parenting"}
def main():
    if not ZIP.is_file():
        raise RuntimeError("Pilot ZIP missing")
    written=[]
    with zipfile.ZipFile(ZIP) as z:
        manifest=json.loads(z.read("manifest.json"))
        images=manifest.get("images",[])
        if len(images)!=12 or {x["profile"] for x in images} != ALLOWED:
            raise RuntimeError("Expected 12 image records from both accounts")
        for profile in ALLOWED:
            if sum(x["profile"]==profile for x in images)!=6:
                raise RuntimeError("Each profile must have six distinct strips")
        for rec in images:
            profile,name=rec["profile"],rec["file"]
            if profile not in ALLOWED or name not in {
              f"{profile}_strip_{i:02}.jpg" for i in range(1,7)
            }:
                raise RuntimeError("Unsafe/unknown comic filename")
            raw=z.read(name)
            if len(raw)!=rec["bytes"] or hashlib.sha256(raw).hexdigest()!=rec["sha256"]:
                raise RuntimeError("Exact image byte checksum mismatch: "+name)
            with Image.open(BytesIO(raw)) as img:
                if img.format!="JPEG" or list(img.size)!=rec["dimensions"]:
                    raise RuntimeError("JPEG format or dimensions mismatch: "+name)
                img.verify()
            target=PREFIX/profile/DAY/name
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() and target.read_bytes()!=raw:
                raise RuntimeError("Existing comic asset differs. Never replace: "+str(target))
            if not target.exists():
                target.write_bytes(raw)
            written.append(str(target.relative_to(ROOT)))
    print(json.dumps({"status":"OK","date":DAY,"assets":written},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
