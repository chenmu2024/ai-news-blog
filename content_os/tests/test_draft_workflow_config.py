"""Regression guard for all seven draft workflows.

Catches the duplicate-permission YAML key that once disabled three bridges,
and catches accidentally removing the source-receipt idempotency preflight.
No third-party packages, no WeChat credentials and no API calls.
"""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ("qiezhi", "wechat", "business", "zizhitongjian",
            "parenting", "jingyun", "fashion")


class WorkflowConfigTests(unittest.TestCase):
    def test_all_bridges_have_unique_permission_keys_and_safe_retries(self):
        for p in PROFILES:
            with self.subTest(profile=p):
                path = ROOT / ".github" / "workflows" / (p + "-draft.yml")
                content = path.read_text(encoding="utf-8")
                self.assertIn("cancel-in-progress: false", content)
                self.assertIn("id: preflight", content)
                self.assertIn("content_os/draft_preflight.py", content)
                self.assertIn("--today-only", content)
                self.assertIn("content_os/publish_readiness.py", content)
                self.assertIn("content_os/image_preflight.py", content)
                self.assertIn("content_os/gate_trace.py", content)
                self.assertIn("timeout-minutes: 5", content)
                self.assertIn("gh workflow run draft-health-audit.yml --ref main", content)
                self.assertLess(content.index("Validate external image bytes"),
                                content.index("Install Chinese fonts"),
                                "Image preflight must precede slow font setup")
                self.assertIn("actions: write", content)
                self.assertIn("--profile " + p, content)
                self.assertIn("steps.preflight.outputs.should_publish", content)
                permissions = content.split("\npermissions:\n", 1)[1].split("\njobs:\n", 1)[0]
                keys = [line.split(":", 1)[0].strip() for line in permissions.splitlines()
                        if re.match(r"^\s{2}[a-z-]+:", line)]
                self.assertEqual(len(keys), len(set(keys)), "Duplicate YAML permissions keys")
                self.assertEqual(keys.count("contents"), 1)
                self.assertEqual(keys.count("actions"), 1)
                self.assertEqual(content.count("      - name: Draft idempotency preflight"), 1)
                self.assertEqual(content.count("cancel-in-progress: true"), 0)

    def test_no_workflow_automatically_broadcasts_or_publishes(self):
        # These are draft bridges; any publication/broadcast actions require
        # a separate explicit user authorization outside this test.
        for p in PROFILES:
            with self.subTest(profile=p):
                text = (ROOT / ".github" / "workflows" / (p+"-draft.yml")).read_text("utf-8")
                self.assertNotIn("publish_to_all", text)
                self.assertNotIn("mass/sendall", text)
                self.assertIn("publish_draft.py", text)


if __name__ == "__main__":
    unittest.main()
