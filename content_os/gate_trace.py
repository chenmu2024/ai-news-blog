"""Bind successful gate reports to exact article bytes; prevents stale PASS reuse."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

GATES = ("quality-gate.json", "visual-gate.json")
EXTRA = {"fashion": ("image-gate.json",), "zizhitongjian": ("source-gate.json",)}


def bind(article: Path, profile: str, root: Path = Path(".")) -> list[str]:
    raw = article.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    paths = list(GATES) + list(EXTRA.get(profile, ()))
    for name in paths:
        path = root / profile / "status" / name
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("status") != "PASS":
            raise ValueError("Cannot bind non-PASS gate: " + str(path))
        report["article_sha256"] = digest
        report["article_path"] = article.as_posix()
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return paths


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--article", type=Path, required=True)
    p.add_argument("--profile", required=True)
    args = p.parse_args()
    print(json.dumps({"bound_gates": bind(args.article, args.profile)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
