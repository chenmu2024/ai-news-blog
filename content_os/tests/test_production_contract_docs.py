"""Fail CI when editorial documentation regresses behind mandatory visual rules."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ProductionContractDocumentationTests(unittest.TestCase):
    def text(self, relative):
        return (ROOT / relative).read_text("utf-8")

    def test_canonical_policy_requires_real_generated_scene_and_no_caption(self):
        policy = self.text("content_os/AI_SCENE_POLICY.md")
        for expected in ("2026-10-13", "generation_id", "SHA256", "图注",
                         "draft/get", "AI原创写实图", "至少5张"):
            with self.subTest(expected=expected):
                self.assertIn(expected, policy)
        self.assertIn("库存图", policy)
        self.assertIn("不能替代", policy)

    def test_c_and_e_comic_direction_cannot_revert_to_policy_or_card_only(self):
        # 2026-10-15 user changed C to healing stories, E back to parenting.
        for profile, must_contain, source in (
            ("business", ("2026-10-15", "暖心", "治愈", "漫画", "F", "不再写"), "business/SOURCE_POLICY.md"),
            ("parenting", ("2026-10-15", "育儿", "孩子", "漫画", "不再做"), "parenting/SOURCE_POLICY.md"),
        ):
            style = self.text(f"{profile}/STYLE.md")
            with self.subTest(profile=profile):
                for phrase in must_contain:
                    self.assertIn(phrase, style)
                self.assertIn("原创", self.text(source))
                self.assertIn("SOURCE_POLICY", style)
        skill=self.text("skills/wechat-comic-content-os/SKILL.md")
        self.assertIn("C：普通人遇到",skill)
        self.assertIn("E：家长与0–12岁孩子",skill)

    def test_historical_photo_policy_kept_without_replacing_comic_requirement(self):
        # The 2026-10-13 real-scene policy remains for old immutable archives.
        old=self.text("content_os/AI_SCENE_POLICY.md")
        self.assertIn("2026-10-13",old)
        self.assertIn("draft/get",old)
        self.assertIn("2026-10-15",self.text("AGENTS.md"))
        self.assertIn("COMIC_PACKAGE",self.text("content_os/PRODUCTION_BRIEF.md"))

    def test_resilience_and_operations_keep_same_precedence(self):
        rules = self.text("content_os/RESILIENCE_POLICY.md")
        operations = self.text("content_os/OPERATIONS.md")
        self.assertIn("不得抵扣必需的AI原创写实图", rules)
        self.assertIn("规则优先级", operations)
        self.assertIn("11:20", operations)
        self.assertIn("不得报告成功", operations)

    def test_archive_not_touched_by_code_only_policy_changes(self):
        import subprocess
        # Documentation tests deliberately never mutate published drafts.
        for profile in ("qiezhi", "wechat", "business", "zizhitongjian",
                        "parenting", "jingyun", "fashion"):
            self.assertTrue((ROOT / profile / "archive").is_dir())

if __name__ == "__main__":
    unittest.main()
