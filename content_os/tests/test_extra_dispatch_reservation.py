"""One-shot extra WeChat dispatch reservation must be durable and fail closed."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from content_os.extra_dispatch_reservation import reserve

TODAY = datetime.now(ZoneInfo("Asia/Shanghai"))
DAY = TODAY.date().isoformat()
ARTICLE_ID = DAY+"--test-unique-story"
PROFILE = "jingyun"
BODY = "# 一个虚构漫画故事\n\n原创虚构漫画故事，不代表真实读者投稿。\n"


class ExtraDispatchReservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.relative = f"{PROFILE}/archive/{ARTICLE_ID}.md"
        self.archive = self.root / self.relative
        self.archive.parent.mkdir(parents=True, exist_ok=True)
        self.archive.write_text(BODY, encoding="utf-8")
        self.approval = self.root / "content_os/draft-approvals" / PROFILE / (ARTICLE_ID+".json")
        self.approval.parent.mkdir(parents=True, exist_ok=True)
        self.approval.write_text(json.dumps({
            "profile": PROFILE, "article_id": ARTICLE_ID,
            "article_sha256": hashlib.sha256(BODY.encode("utf-8")).hexdigest(),
            "status": "approved", "approved_by": "user", "source": "chat",
            "approved_at": TODAY.isoformat(),
            "user_confirmation": "同步草稿",
            "previewed_with_real_images": True
        }, ensure_ascii=False), encoding="utf-8")

    def test_exact_approved_article_reserved_once(self):
        result = reserve(self.root, PROFILE, self.relative, now=TODAY)
        self.assertEqual(result["status"], "RESERVED_NO_DISPATCH_YET")
        marker = self.root / result["reservation_path"]
        self.assertTrue(marker.exists())
        self.assertEqual(json.loads(marker.read_text("utf-8"))["article_id"], ARTICLE_ID)
        with self.assertRaisesRegex(ValueError, "prior_dispatch_reservation_exists"):
            reserve(self.root, PROFILE, self.relative, now=TODAY)

    def test_missing_or_stale_explicit_approval_blocks(self):
        self.approval.unlink()
        with self.assertRaisesRegex(ValueError, "exact_user_approval_missing"):
            reserve(self.root, PROFILE, self.relative, now=TODAY)
        self.assertFalse((self.root / f"content_os/dispatch-reservations/{PROFILE}/{ARTICLE_ID}.json").exists())

    def test_attempted_journal_blocks_without_reservation(self):
        journal = self.root / PROFILE / "status/draft-attempts" / (ARTICLE_ID+".json")
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text('{"state":"attempted"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already_attempted_confirmed_or_unknown"):
            reserve(self.root, PROFILE, self.relative, now=TODAY)

    def test_mismatched_article_date_blocks(self):
        from datetime import timedelta
        with self.assertRaisesRegex(ValueError, "not_today_no_late_dispatch"):
            reserve(self.root, PROFILE, self.relative, now=TODAY+timedelta(days=1))

    def test_no_directory_traversal(self):
        with self.assertRaisesRegex(ValueError, "repo_relative"):
            reserve(self.root, PROFILE, "../untrusted.md", now=TODAY)


if __name__ == "__main__":
    unittest.main()
