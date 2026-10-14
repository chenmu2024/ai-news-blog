"""Non-publishing candidate validation against the REAL 30-day archive history.

This must run BEFORE GitHub create_file creates an immutable archive.
It never calls WeChat or modifies any persisted account status/Gate.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

try:
    from content_os.publish_readiness import check as publisher_check
    from content_os.editorial_guard import assess_editorial_title
except ImportError:
    from publish_readiness import check as publisher_check
    from editorial_guard import assess_editorial_title

ROOT = Path(__file__).resolve().parents[1]
# Direct execution (python content_os/prearchive_validate.py) has content_os/
# on sys.path, not necessarily the repository root. Required for fashion gate.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROFILES = ("qiezhi", "wechat", "business", "zizhitongjian",
            "parenting", "jingyun", "fashion")
QUALITY_NAMES = {"wechat": "ai_business", "business": "business_story"}

def _title(text: str) -> str:
    return next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")

def fashion_evergreen_star_repeat(archive_dir: Path, day: str, title: str) -> bool:
    """Reject repeated same-celebrity evergreen five-look collections in 14 days."""
    aliases = {
        "jisoo": ("jisoo", "金智秀"),
        "jennie": ("jennie", "金珍妮"),
        "rose": ("rosé", "rose", "朴彩英"),
        "lisa": ("lisa", "lalisa", "丽莎"),
        "sana": ("sana", "凑崎纱夏", "湊﨑紗夏"),
        "宋慧乔": ("宋慧乔", "song hyekyo"),
        "iu": ("李知恩", "iu", "lee ji-eun"),
    }
    def people(v):
        t=v.casefold()
        return {person for person,forms in aliases.items()
                if any(form.casefold() in t for form in forms)}
    def is_roundup(v):
        return (bool(re.search(r"(?:[4-9]|四|五|六|七|八|九)[套张组次]", v))
                and bool(re.search(r"造型|穿搭|旧照|照片|亮相|经典|同款",v)))
    if not is_roundup(title):
        return False
    stars=people(title)
    if not stars:
        return False
    for old in archive_dir.glob("????-??-??.md"):
        try:
            days=(date.fromisoformat(day)-date.fromisoformat(old.stem)).days
        except ValueError:
            continue
        if 0 < days <= 14:
            old_title=_title(old.read_text("utf-8"))
            if is_roundup(old_title) and stars.intersection(people(old_title)):
                return True
    return False


def static_check(root: Path, profile: str, day: str, text: str, *, article_id: str | None = None) -> dict:
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Invalid day")
    from content_os.multi_draft import validate_article_id
    article_id = validate_article_id(day, article_id or day)
    errors = []
    if article_id != day:
        from content_os.multi_draft import verify_extra_approval
        errors.extend(verify_extra_approval(root,profile,article_id,text))
    archive = root / profile / "archive" / f"{article_id}.md"
    journal = root / profile / "status" / "draft-attempts" / f"{article_id}.json"
    status_path = root / profile / "status" / "latest.json"
    # Never overwrite an existing article, even if draft publishing failed.
    if archive.exists():
        errors.append("today_archive_already_exists_never_overwrite")
    if journal.exists():
        errors.append("draft_add_attempt_journal_present_manual_review_only")
    if status_path.exists():
        try:
            prior = json.loads(status_path.read_text("utf-8"))
            if prior.get("article_path") == f"{profile}/archive/{article_id}.md":
                errors.append("today_draft_receipt_exists_never_duplicate")
        except (ValueError, OSError):
            errors.append("unreadable_status_requires_manual_review")
    readiness = publisher_check(profile, text, day)
    errors.extend("publisher: " + x for x in readiness["errors"])
    from content_os.editorial_review import check as editorial_check
    review = editorial_check(root, profile, day, text, article_id=article_id)
    errors.extend("editorial_review: " + x for x in review["errors"])
    # Real archive folder is authoritative; /tmp article paths do not carry
    # title-duplication history. Compare the proposed title to it directly.
    audit_profile = QUALITY_NAMES.get(profile, profile)
    editorial = assess_editorial_title(
        audit_profile, archive, _title(text), archive_dir=archive.parent)
    errors.extend("editorial: " + x for x in editorial["reasons"])
    # Some accounts lack specialized template guards, so enforce literal
    # normalized 30-day title de-dup across ALL seven account profiles.
    from content_os.editorial_guard import normalize_title
    current = normalize_title(_title(text))
    for past in archive.parent.glob("*.md"):
        if past.stem == article_id:
            continue
        try:
            older = date.fromisoformat(past.stem[:10])
        except ValueError:
            continue
        if older <= date.fromisoformat(day) and (date.fromisoformat(day) - older).days <= 30:
            previous = _title(past.read_text("utf-8"))
            if current and normalize_title(previous) == current:
                errors.append("30day_exact_duplicate_title")
                break
    if profile == "fashion":
        if fashion_evergreen_star_repeat(archive.parent, day, _title(text)):
            errors.append("fashion: repeated celebrity outfit roundup within 14 days")
        from fashion.image_gate import celebrity_quota_error, SOURCE_RE
        m = SOURCE_RE.search(text)
        if m:
            try:
                data = json.loads(m.group(1))
                quota = celebrity_quota_error(archive, data.get("topic_type", ""))
                if quota:
                    errors.append("fashion: " + quota)
                if day >= "2026-10-11":
                    images = data.get("images", [])
                    if not isinstance(images, list) or len(images) < 5:
                        errors.append("fashion: five real image source records required")
                    else:
                        for idx, image in enumerate(images, 1):
                            if (not isinstance(image, dict)
                                or image.get("verified") is not True
                                or not str(image.get("source_page_url") or "").startswith("https://")
                                or image.get("rights") in (None, "", "unknown", "unknown_public", "ai_generated")):
                                errors.append(f"fashion: unverified rights/source on photo {idx}")
            except (ValueError, TypeError, AttributeError):
                errors.append("fashion: malformed source manifest")
    return {
        "status": "FAIL" if errors else "PASS",
        "profile": profile,
        "date": day,
        "archive": f"{profile}/archive/{article_id}.md",
        "title": _title(text),
        "readiness": readiness["status"],
        "editorial": editorial["status"],
        "errors": list(dict.fromkeys(errors))
    }

def validate(root: Path, profile: str, day: str, article: Path,
             skip_image_network: bool = False, *, article_id: str | None = None) -> dict:
    content = article.read_bytes().decode("utf-8")
    result = static_check(root, profile, day, content, article_id=article_id)
    result["checks"] = []
    if result["status"] != "PASS":
        return result
    # Shadow archive prevents source/image gates from assuming a random
    # temporary basename while keeping immutable on-disk archives untouched.
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / profile / "archive" / f"{article_id or day}.md"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(content, "utf-8")
        # Validate fashion's 7-day celebrity quota against the REAL prior archive
        # history, not an empty temporary directory.
        if profile == "fashion":
            target_date = date.fromisoformat(day)
            for prior in (root / "fashion" / "archive").glob("????-??-??.md"):
                try:
                    age = (target_date - date.fromisoformat(prior.stem)).days
                except ValueError:
                    continue
                if 0 < age <= 6:
                    (staged.parent / prior.name).write_bytes(prior.read_bytes())
        quality_profile = QUALITY_NAMES.get(profile, profile)
        commands = [
            ("humanizer", [sys.executable, str(root/"content_os/humanizer/humanizer_gate.py"),
                           "--profile", profile, "--article", str(staged), "--date", day]),
            ("humanizer_pollution", [sys.executable, str(root/"content_os/humanizer/pollution_gate.py"),
                                     "--profile", profile, "--date", day, "--root", str(root)]),
            ("quality", [sys.executable, str(root/"content_os/quality_gate.py"),
                         "--profile", quality_profile, "--article", str(staged)]),
            ("visual", [sys.executable, str(root/"content_os/visual_gate.py"),
                        "--profile", quality_profile, "--article", str(staged)]),
        ]
        if profile == "zizhitongjian":
            commands.append(("source", [sys.executable, str(root/"zizhitongjian/source_gate.py"),
                                        "--article", str(staged)]))
        if profile == "fashion":
            commands.append(("fashion_image", [sys.executable, str(root/"fashion/image_gate.py"),
                                              "--article", str(staged)]))
        if not skip_image_network:
            commands.append(("image_bytes", [sys.executable, str(root/"content_os/image_preflight.py"),
                                             "--profile", profile, "--article", str(staged)]))
        for name, command in commands:
            try:
                process = subprocess.run(command, cwd=root, capture_output=True,
                                         text=True, timeout=360, check=False)
                rc = process.returncode
                tail = (process.stdout + "\n" + process.stderr)[-2200:]
            except subprocess.TimeoutExpired:
                rc = 124
                tail = "check_timed_out"
            result["checks"].append({"name": name, "exit_code": rc, "log_tail": tail})
            if rc != 0:
                result["status"] = "FAIL"
                result["errors"].append(f"{name}_gate_failed_or_warn_{rc}")
                # Don't spend time downloading images when offline gates fail.
                break
    return result

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=PROFILES)
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--article-id", help="Immutable article ID, YYYY-MM-DD or YYYY-MM-DD--slug")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-image-network", action="store_true",
                        help="Offline diagnostics only. NEVER proof of publish readiness.")
    args = parser.parse_args()
    result = validate(args.root.resolve(), args.profile, args.date,
                      args.article.resolve(), args.skip_image_network, article_id=args.article_id)
    if args.skip_image_network:
        result["network_verification"] = "NOT_RUN_NEVER_PUBLISH_ON_THIS_RESULT"
        # Even structurally clean drafts are NOT fully approved.
        result["status"] = "INCOMPLETE" if result["status"] == "PASS" else result["status"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
