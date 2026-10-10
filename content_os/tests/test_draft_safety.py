import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import draft_preflight as preflight
import daily_healthcheck as health


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.arc = self.root / "fashion" / "archive" / "2026-10-08.md"
        self.arc.parent.mkdir(parents=True)
        self.arc.write_text("# Title\n\nSample.", encoding="utf-8")
        self.status = self.root / "fashion" / "status"
        self.status.mkdir(parents=True)
        self.digest = hashlib.sha256(self.arc.read_bytes()).hexdigest()

    def test_first_attempt_must_publish(self):
        self.assertTrue(preflight.inspect(self.arc, "fashion", self.status)["should_publish"])

    def test_confirmed_receipt_blocks_duplicate(self):
        (self.status / "latest.json").write_text(json.dumps({
            "status": "success", "title": "Title", "article_sha256": self.digest,
            "article_path": self.arc.as_posix(),
        }), encoding="utf-8")
        self.assertFalse(preflight.inspect(self.arc, "fashion", self.status)["should_publish"])

    def test_changed_article_must_not_share_old_receipt(self):
        (self.status / "latest.json").write_text(json.dumps({
            "status": "success", "title": "Title", "article_sha256": self.digest,
            "article_path": self.arc.as_posix(),
        }), encoding="utf-8")
        self.arc.write_text("# Title\n\nRevision.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "successful WeChat draft"):
            preflight.inspect(self.arc, "fashion", self.status)

    def test_unknown_draft_add_result_must_never_retry(self):
        journal = self.status / "draft-attempts"
        journal.mkdir()
        (journal / "2026-10-08.json").write_text(json.dumps({
            "state": "attempted", "article_sha256": self.digest,
            "article_path": self.arc.as_posix(), "run_id": "123"
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "durable journal"):
            preflight.inspect(self.arc, "fashion", self.status)

    def test_confirmed_journal_without_latest_receipt_must_not_repost(self):
        journal = self.status / "draft-attempts"
        journal.mkdir()
        (journal / "2026-10-08.json").write_text(json.dumps({
            "state": "confirmed", "article_sha256": self.digest,
            "draft_media_id": "test-media-id",
            "article_path": self.arc.as_posix(), "run_id": "123"
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "durable journal"):
            preflight.inspect(self.arc, "fashion", self.status)

    def test_stale_or_failed_receipt_must_not_block(self):
        (self.status / "latest.json").write_text(json.dumps({
            "status": "failure", "title": "Title", "article_sha256": self.digest,
        }), encoding="utf-8")
        self.assertTrue(preflight.inspect(self.arc, "fashion", self.status)["should_publish"])


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.day = "2026-10-08"

    def create_profile(self, profile: str) -> None:
        base = self.root / profile
        (base / "archive").mkdir(parents=True)
        (base / "articles").mkdir(parents=True)
        (base / "status").mkdir(parents=True)
        text = "# Example title\n\nVerified daily article"
        (base / "archive" / (self.day + ".md")).write_text(text, encoding="utf-8")
        (base / "articles" / "today.md").write_text(text, encoding="utf-8")
        content = text.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        (base / "status" / "latest.json").write_text(
            json.dumps({"status": "success", "article_sha256": digest, "title": "Example title",
                        "article_path": profile + "/archive/" + self.day + ".md"}), encoding="utf-8")
        gates = ["quality-gate.json", "visual-gate.json"]
        if profile == "fashion": gates += ["image-gate.json"]
        if profile == "zizhitongjian": gates += ["source-gate.json"]
        for name in gates:
            (base / "status" / name).write_text(json.dumps({"status": "PASS"}), encoding="utf-8")

    def test_complete_requires_all_seven(self):
        for p in health.PROFILES:
            self.create_profile(p)
        result = health.make_report(self.root, self.day)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["success_count"], 7)

    def test_future_date_refuses_stale_gate_and_missing_journal(self):
        self.day = "2026-10-11"
        self.create_profile("business")
        state = health.audit_profile(self.root, "business", self.day)
        self.assertIn("draft_add_journal_missing_or_unconfirmed", state["errors"])
        self.assertIn("gate_not_bound_to_archive:quality-gate.json", state["errors"])

    def test_future_date_validated_with_bound_gates_and_confirmed_media_id(self):
        self.day = "2026-10-11"
        self.create_profile("business")
        base = self.root / "business"
        raw = (base / "archive" / "2026-10-11.md").read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        for gate in ("quality-gate.json", "visual-gate.json"):
            (base / "status" / gate).write_text(json.dumps({
                "status": "PASS", "article_sha256": digest,
                "article_path": "business/archive/2026-10-11.md"
            }), encoding="utf-8")
        journal = base / "status" / "draft-attempts"
        journal.mkdir()
        (journal / "2026-10-11.json").write_text(json.dumps({
            "state": "confirmed", "draft_media_id": "receipt-123",
            "article_sha256": digest, "article_path": "business/archive/2026-10-11.md"
        }), encoding="utf-8")
        state = health.audit_profile(self.root, "business", self.day)
        self.assertEqual(state["status"], "success")

    def test_detects_missing_today_file(self):
        self.create_profile("jingyun")
        (self.root / "jingyun" / "articles" / "today.md").unlink()
        state = health.audit_profile(self.root, "jingyun", self.day)
        self.assertIn("today_missing", state["errors"])

    def test_detects_stale_receipt(self):
        self.create_profile("business")
        path = self.root / "business" / "status" / "latest.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["article_sha256"] = "0" * 64
        path.write_text(json.dumps(record), encoding="utf-8")
        result = health.audit_profile(self.root, "business", self.day)
        self.assertIn("receipt_sha_mismatch_or_stale", result["errors"])

    def test_no_false_healthy_status_with_no_archive(self):
        result = health.make_report(self.root, self.day)
        self.assertEqual(result["success_count"], 0)
        self.assertEqual(result["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
