import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editorial_guard import assess_editorial_title, parenting_template_family


class EditorialGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "archive"
        self.archive.mkdir()
        self.write("2026-10-08", "孩子作业拖到深夜，很多家长第一步就问错了")
        self.write("2026-10-09", "孩子早上说不想去学校，先别急着问为什么又闹")

    def write(self, day, title):
        f = self.archive / (day + ".md")
        f.write_text("# " + title + "\n\n正文。", encoding="utf-8")
        return f

    def test_existing_archived_article_is_not_retroactively_blocked(self):
        f = self.archive / "2026-10-09.md"
        state = assess_editorial_title("parenting", f,
                                       "孩子早上说不想去学校，先别急着问为什么又闹")
        self.assertEqual(state["status"], "SKIP")

    def test_next_repetitive_parenting_pattern_is_blocked(self):
        f = self.write("2026-10-10", "孩子作业多到写不完，父母先别急着责备")
        state = assess_editorial_title("parenting", f,
                                       "孩子作业多到写不完，父母先别急着责备")
        self.assertEqual(state["status"], "FAIL")
        self.assertIn("重复模板", state["reasons"][0])
        self.assertEqual(state["compared"], 2)

    def test_new_education_realities_angle_is_allowed(self):
        title = "家长群里一条通知，为什么让几位父母争论了整晚？"
        f = self.write("2026-10-10", title)
        state = assess_editorial_title("parenting", f, title)
        self.assertEqual(state["status"], "PASS")
        self.assertIsNone(parenting_template_family(title))

    def test_exact_near_30day_duplicate_is_blocked(self):
        title = "孩子早上说不想去学校，先别急着问为什么又闹"
        f = self.write("2026-10-10", title)
        state = assess_editorial_title("parenting", f, title)
        self.assertEqual(state["status"], "FAIL")
        self.assertTrue(any("完全重复" in reason for reason in state["reasons"]))

    def test_business_not_banned_for_brand_itself(self):
        title = "瑞幸为什么开始改变它的低价生意？"
        f = self.write("2026-10-10", title)
        state = assess_editorial_title("business_story", f, title)
        self.assertEqual(state["status"], "PASS")

    def test_non_profile_unaffected(self):
        f = self.write("2026-10-10", "孩子早上说不想去学校，先别急着问为什么又闹")
        self.assertEqual(assess_editorial_title("qiezhi", f, "abc")["status"], "SKIP")


if __name__ == "__main__":
    unittest.main()
