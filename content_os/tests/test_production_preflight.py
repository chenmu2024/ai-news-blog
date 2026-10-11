"""Regression for nonblocking research and fail-closed seven-account handoff."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from production_preflight import inspect


class ProductionHandoffTests(unittest.TestCase):
    DATE = "2026-10-11"

    def test_missing_stale_research_does_not_block_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "content_os/daily-health").mkdir(parents=True)
            (root / "content_os/daily-health/latest.json").write_text('{"date":"2026-10-10"}')
            report = inspect(root, self.DATE)
            self.assertEqual(len(report["missing_archives"]), 7)
            self.assertEqual(report["profiles"]["qiezhi"]["action"], "write_new_archive")
            self.assertFalse(report["input_freshness"]["daily_health"]["fresh"])

    def test_yesterdays_success_never_counts_as_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "qiezhi/status/latest.json"
            f.parent.mkdir(parents=True)
            f.write_text('{"status":"success","article_path":"qiezhi/archive/2026-10-10.md"}')
            self.assertEqual(inspect(root, self.DATE)["profiles"]["qiezhi"]["action"], "write_new_archive")

    def test_attempt_journal_is_never_auto_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "fashion/status/draft-attempts/2026-10-11.json"
            f.parent.mkdir(parents=True)
            f.write_text('{"state":"attempted"}')
            r = inspect(root, self.DATE)["profiles"]["fashion"]
            self.assertEqual(r["action"], "manual_review_required")

    def test_today_receipt_without_journal_blocks_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "wechat/status/latest.json"
            f.parent.mkdir(parents=True)
            f.write_text('{"status":"success","article_path":"wechat/archive/2026-10-11.md"}')
            self.assertEqual(inspect(root, self.DATE)["profiles"]["wechat"]["action"], "manual_review_required")

    def test_existing_archive_without_journal_needs_actions_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "business/archive/2026-10-11.md"
            f.parent.mkdir(parents=True)
            f.write_text("# Some title\n")
            self.assertEqual(inspect(root, self.DATE)["profiles"]["business"]["action"],
                             "inspect_actions_before_dispatch")


if __name__ == "__main__":
    unittest.main()
