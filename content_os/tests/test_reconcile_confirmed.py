"""Offline recovery tests: no WeChat calls, no GitHub network."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reconcile_confirmed as recovery


class ConfirmedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = "business"
        self.day = "2026-10-11"
        self.base = self.root / self.profile
        self.archive = self.base / "archive" / (self.day + ".md")
        self.archive.parent.mkdir(parents=True)
        self.archive.write_text("# 本日瑞幸故事\n\n真实原创文章。", "utf-8")
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.status = self.base / "status"
        self.status.mkdir()
        self.journal_dir = self.status / "draft-attempts"
        self.journal_dir.mkdir()
        self.intent = {
            "state": "confirmed",
            "profile": self.profile,
            "article_path": f"{self.profile}/archive/{self.day}.md",
            "article_sha256": self.digest,
            "title": "本日瑞幸故事",
            "run_id": "run-123",
            "draft_media_id": "media-real-from-WeChat",
            "passed_gates": {
                gate: {"status": "PASS", "article_path": f"{self.profile}/archive/{self.day}.md",
                       "article_sha256": self.digest}
                for gate in ("quality-gate.json", "visual-gate.json")
            },
        }
        self.write_intent()

    def write_intent(self):
        (self.journal_dir / (self.day + ".json")).write_text(
            json.dumps(self.intent, ensure_ascii=False), "utf-8")

    def test_recovers_confirmed_draft_without_wechat_post(self):
        result = recovery.reconcile(self.root, self.profile, self.day)
        self.assertEqual(result["result"], "recovered_confirmed_without_wechat_call")
        latest = json.loads((self.status / "latest.json").read_text("utf-8"))
        self.assertEqual(latest["article_sha256"], self.digest)
        self.assertEqual(latest["draft_media_id"], self.intent["draft_media_id"])
        self.assertEqual((self.base / "articles/today.md").read_bytes(), self.archive.read_bytes())
        for name in ("quality-gate.json", "visual-gate.json"):
            self.assertEqual(json.loads((self.status / name).read_text("utf-8")),
                             self.intent["passed_gates"][name])
        self.assertEqual(recovery.reconcile(self.root, self.profile, self.day)["result"],
                         "already_confirmed")

    def test_recovery_keeps_wechat_image_readback_in_visual_gate(self):
        self.day = "2026-10-13"
        self.archive = self.base / "archive" / (self.day + ".md")
        self.archive.write_text("# 本日瑞幸故事\n\n真实原创文章。", "utf-8")
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        rel = f"{self.profile}/archive/{self.day}.md"
        self.intent.update({
            "article_path": rel, "article_sha256": self.digest,
            "passed_gates": {
                key: {"status": "PASS", "article_path": rel,
                      "article_sha256": self.digest}
                for key in ("quality-gate.json", "visual-gate.json")
            },
        })
        self.write_intent()
        proof = {
            "draft_get_verified": True,
            "draft_media_id": self.intent["draft_media_id"],
            "article_path": rel, "article_sha256": self.digest,
            "article_date": self.day, "inline_image_count": 2,
        }
        out = self.status / "draft-readback" / (self.day + ".json")
        out.parent.mkdir()
        out.write_text(json.dumps(proof), "utf-8")
        result = recovery.reconcile(self.root, self.profile, self.day)
        self.assertEqual(result["result"], "recovered_confirmed_without_wechat_call")
        gate = json.loads((self.status / "visual-gate.json").read_text("utf-8"))
        self.assertEqual(gate["wechat_inline_readback"], proof)

    def test_attempted_is_never_recovered(self):
        self.intent["state"] = "attempted"
        self.write_intent()
        result = recovery.reconcile(self.root, self.profile, self.day)
        self.assertEqual(result["result"], "skip_no_confirmed_journal")
        self.assertFalse((self.status / "latest.json").exists())

    def test_changed_archive_is_never_recovered(self):
        self.archive.write_text("# 内容变化\n", "utf-8")
        result = recovery.reconcile(self.root, self.profile, self.day)
        self.assertEqual(result["result"], "blocked_journal_archive_conflict")
        self.assertFalse((self.status / "latest.json").exists())

    def test_missing_gate_snapshot_blocks_recovery(self):
        del self.intent["passed_gates"]
        self.write_intent()
        self.assertEqual(recovery.reconcile(self.root, self.profile, self.day)["result"],
                         "blocked_missing_gate_snapshot")
        self.assertFalse((self.status / "latest.json").exists())

    def test_same_day_existing_conflicting_receipt_is_immutable(self):
        old = {"status": "success", "title": "不同标题",
               "article_path": f"{self.profile}/archive/{self.day}.md",
               "article_sha256": "0"*64}
        (self.status / "latest.json").write_text(json.dumps(old), "utf-8")
        self.assertEqual(recovery.reconcile(self.root, self.profile, self.day)["result"],
                         "blocked_existing_receipt_conflict")
        self.assertEqual(json.loads((self.status / "latest.json").read_text("utf-8")), old)

    def test_older_day_success_can_be_safely_superseded(self):
        old = {"status": "success", "title": "昨日故事",
               "article_path": "business/archive/2026-10-10.md",
               "article_sha256": "0"*64}
        (self.status / "latest.json").write_text(json.dumps(old), "utf-8")
        self.assertEqual(recovery.reconcile(self.root, self.profile, self.day)["result"],
                         "recovered_confirmed_without_wechat_call")


if __name__ == "__main__":
    unittest.main()
