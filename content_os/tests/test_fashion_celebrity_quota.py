"""Celebrity mix gates must fail early without rewriting a successful draft."""
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fashion_image_gate", ROOT / "fashion/image_gate.py")
fashion_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fashion_gate)


class CelebrityMixTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.archive = Path(self.t.name) / "fashion/archive"
        self.archive.mkdir(parents=True)
        self.start = date(2026, 10, 11)

    def put(self, n, kind):
        day = (self.start + timedelta(days=n)).isoformat()
        f = self.archive / f"{day}.md"
        manifest = {"topic_type": kind, "subject": "某明星" if kind == "celebrity" else "通勤"}
        f.write_text("<!-- FASHION_SOURCE\n" + json.dumps(manifest, ensure_ascii=False) +
                     "\n-->\n# 标题\n", "utf-8")
        return f

    def test_five_seven_blocks_third_generic_article(self):
        self.put(0, "japanese")
        self.put(1, "korean")
        f = self.put(2, "lookbook")
        self.assertIn("至少5篇", fashion_gate.celebrity_quota_error(f, "lookbook"))
        self.assertIsNone(fashion_gate.celebrity_quota_error(f, "celebrity"))

    def test_five_celebrities_allow_two_generic_posts(self):
        for i in range(5):
            self.put(i, "celebrity")
        f = self.put(5, "japanese")
        self.assertIsNone(fashion_gate.celebrity_quota_error(f, "japanese"))
        f = self.put(6, "korean")
        self.assertIsNone(fashion_gate.celebrity_quota_error(f, "korean"))

    def test_new_seven_day_block_resets_quota(self):
        self.put(0, "japanese")
        self.put(1, "korean")
        f = self.put(7, "korean")
        self.assertIsNone(fashion_gate.celebrity_quota_error(f, "korean"))

    def test_old_archive_and_inplace_revision_unaffected(self):
        old = self.archive / "2026-10-10.md"
        old.write_text("# 日本街拍\n", "utf-8")
        self.assertIsNone(fashion_gate.celebrity_quota_error(old, "japanese"))
        revision = Path(self.t.name) / "fashion/revisions/2026-10-11.md"
        revision.parent.mkdir(parents=True)
        revision.write_text("# 修改草稿\n", "utf-8")
        self.assertIsNone(fashion_gate.celebrity_quota_error(revision, "japanese"))


if __name__ == "__main__":
    unittest.main()
