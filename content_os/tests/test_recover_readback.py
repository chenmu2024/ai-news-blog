"""Offline tests for read-only recovery: fake HTTP, no WeChat side effects."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from content_os import recover_readback as m


class ReadbackRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        self.before = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(lambda: os.chdir(self.before))
        self.profile = "business"
        self.day = "2026-10-13"
        self.archive = self.root / self.profile / "archive" / (self.day + ".md")
        self.archive.parent.mkdir(parents=True)
        self.archive.write_text("# 测试标题\n\n原创正文\n", "utf-8")
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.relative = f"{self.profile}/archive/{self.day}.md"
        self.expected = "https://mmbiz.qpic.cn/mmbiz_jpg/unique_uploaded_fingerprint/0"
        gate = {"status": "PASS", "article_sha256": self.sha,
                "article_path": self.relative}
        status = self.root / self.profile / "status"
        status.mkdir(parents=True)
        (status / "visual-gate.json").write_text(json.dumps(gate), "utf-8")
        self.journal = status / "draft-attempts" / (self.day + ".json")
        self.journal.parent.mkdir(parents=True)
        self.journal.write_text(json.dumps({
            "profile": self.profile, "state": "confirmed",
            "title": "测试标题", "article_path": self.relative,
            "article_sha256": self.sha, "draft_media_id": "existing-media-id",
            "expected_inline_urls": [self.expected],
            "passed_gates": {"quality-gate.json": gate, "visual-gate.json": gate},
        }), "utf-8")

    def test_refuses_attempted_and_conflicting_journals_without_http(self):
        data = json.loads(self.journal.read_text("utf-8"))
        for edit in ({"state": "attempted"}, {"article_sha256": "0" * 64},
                     {"expected_inline_urls": []},
                     {"passed_gates": {}}):
            with self.subTest(edit=edit):
                self.journal.write_text(json.dumps({**data, **edit}), "utf-8")
                client = Mock()
                result = m.recover_one(self.root, self.profile, self.day,
                                       transport=client, credentials=("a", "b"))
                self.assertNotEqual(result["result"], "recovered_verified_existing_draft")
                client.assert_not_called()

    def test_recovery_calls_only_token_and_draft_get(self):
        def reply(content):
            out = Mock()
            out.json.return_value = content
            return out
        def request(method, url, **kwargs):
            if url.endswith("/token"):
                return reply({"access_token": "test-access-token"})
            self.assertTrue(url.endswith("/draft/get"))
            self.assertEqual(kwargs["data"].decode("utf-8"),
                             '{"media_id": "existing-media-id"}')
            return reply({"news_item": [{"title": "测试标题",
                "content": '<section><img src="' + self.expected + '" /></section>'}]})
        fake = Mock(side_effect=request)
        result = m.recover_one(self.root, self.profile, self.day, fake, ("a", "b"))
        self.assertEqual(result["result"], "recovered_verified_existing_draft")
        self.assertEqual(fake.call_count, 2)
        self.assertEqual([x.args[0] for x in fake.call_args_list], ["GET", "POST"])
        self.assertFalse(any("/draft/add" in x.args[1] for x in fake.call_args_list))
        record = m.read(self.root / self.profile / "status/draft-readback" / (self.day + ".json"))
        self.assertTrue(record["draft_get_verified"])
        self.assertEqual(record["article_sha256"], self.sha)
        gate = m.read(self.root / self.profile / "status/visual-gate.json")
        self.assertEqual(gate["wechat_inline_readback"]["draft_media_id"],
                         "existing-media-id")
        fake.reset_mock()
        result = m.recover_one(self.root, self.profile, self.day, fake, ("a", "b"))
        self.assertEqual(result["result"], "skip_already_readback_verified")
        fake.assert_not_called()

    def test_title_mismatch_records_safe_evidence_with_no_draft_write(self):
        def fake(method, url, **kwargs):
            response = Mock()
            response.json.return_value = (
                {"access_token": "example-token"} if url.endswith("/token")
                else {"news_item": [{"title": "微信不同标题",
                                     "content": '<img src="' + self.expected + '" />'}]})
            return response
        transport = Mock(side_effect=fake)
        outcome = m.recover_one(self.root, self.profile, self.day,
                                transport=transport, credentials=("app-id", "app-secret"))
        self.assertEqual(outcome["result"], "readback_failed")
        path = self.root / self.profile / "status" / "draft-readback-diagnostic" / (self.day + ".json")
        evidence = json.loads(path.read_text("utf-8"))
        self.assertEqual(evidence["expected_title"], "测试标题")
        self.assertEqual(evidence["observed_title"], "微信不同标题")
        self.assertTrue(evidence["no_write_operation"])
        self.assertNotIn("app-secret", path.read_text("utf-8"))
        self.assertTrue(all(not x.args[1].endswith("/draft/add") for x in transport.call_args_list))

    def test_network_failure_is_reported_without_leaking_token_or_secret(self):
        bad = Mock(side_effect=RuntimeError("SHOULD_NOT_LEAK_TEST_SECRET"))
        result = m.recover_one(self.root, self.profile, self.day,
                               transport=bad, credentials=("a", "secret"))
        self.assertEqual(result["result"], "readback_failed")
        self.assertNotIn("secret", json.dumps(result).lower())
        self.assertNotIn("SHOULD_NOT_LEAK", json.dumps(result))

if __name__ == "__main__":
    unittest.main()
