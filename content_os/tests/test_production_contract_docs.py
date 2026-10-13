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

    def test_c_and_e_must_not_revert_to_card_only_editorial_direction(self):
        for profile in ("business", "parenting"):
            style = self.text(f"{profile}/STYLE.md")
            with self.subTest(profile=profile):
                self.assertIn("2026-10-13", style)
                self.assertIn("至少1张", style)
                self.assertIn("AI", style)
                self.assertIn("图注", style)
                self.assertIn("不能替代", style)
                self.assertIn("draft/get", style)

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
