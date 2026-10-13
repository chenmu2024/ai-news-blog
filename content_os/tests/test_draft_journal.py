"""Offline tests for write-ahead draft/add idempotency, no GitHub or WeChat requests."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import draft_journal as journal

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ("qiezhi", "wechat", "business", "zizhitongjian",
            "parenting", "jingyun", "fashion")


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.article = Path(self.temp.name) / "business" / "archive" / "2026-10-11.md"
        self.article.parent.mkdir(parents=True)
        self.article.write_text("# 新稿\n\n原创文章", encoding="utf-8")
        self.state = {}
        self.fake_gate = patch.object(journal, "gate_snapshot", return_value={
            "quality-gate.json": {"status": "PASS"},
            "visual-gate.json": {"status": "PASS"},
        })
        self.fake_env = patch.object(journal, "_environment",
                                     return_value=("test-token", "example/repo", "run-11"))
        self.fake_get = patch.object(journal, "_get", side_effect=self.get)
        self.fake_put = patch.object(journal, "_put", side_effect=self.put)
        for item in (self.fake_gate, self.fake_env, self.fake_get, self.fake_put):
            item.start()
            self.addCleanup(item.stop)

    def get(self, token, repo, path):
        if path in self.state:
            return dict(self.state[path]), "blob"
        return None, None

    def put(self, token, repo, path, data, sha):
        self.state[path] = dict(data)

    def test_before_draft_add_is_persisted_and_double_attempt_is_blocked(self):
        journal.reserve("business", self.article, "新稿")
        key = journal.journal_path("business", self.article)
        self.assertEqual(self.state[key]["state"], "attempted")
        self.assertEqual(self.state[key]["article_sha256"],
                         hashlib.sha256(self.article.read_bytes()).hexdigest())
        with self.assertRaisesRegex(RuntimeError, "already attempted"):
            journal.reserve("business", self.article, "新稿")

    def test_new_draft_requires_uploaded_wechat_image_and_records_exact_urls(self):
        new = self.article.with_name("2026-10-13.md")
        new.write_text("# 新稿\n\n正文", "utf-8")
        with self.assertRaisesRegex(RuntimeError, "required inline WeChat images"):
            journal.reserve("business", new, "新稿", public_body_html="<p>No image</p>")
        image_url = "https://mmbiz.qpic.cn/mmbiz_jpg/specific_fingerprint/0"
        body = f'<p><img src="{image_url}" /></p>'
        journal.reserve("business", new, "新稿", public_body_html=body)
        key = journal.journal_path("business", new)
        self.assertEqual(self.state[key]["expected_inline_urls"], [image_url])
        with self.assertRaisesRegex(RuntimeError, "already attempted"):
            journal.reserve("business", new, "新稿", public_body_html=body)

    def test_media_id_is_confirmed_durably(self):
        journal.reserve("business", self.article, "新稿")
        journal.confirm("business", self.article, "media-confirmed-123")
        key = journal.journal_path("business", self.article)
        self.assertEqual(self.state[key]["state"], "confirmed")
        self.assertEqual(self.state[key]["draft_media_id"], "media-confirmed-123")
        journal.confirm("business", self.article, "media-confirmed-123")
        with self.assertRaisesRegex(RuntimeError, "media_id conflict"):
            journal.confirm("business", self.article, "different-media-id")

    def test_new_draft_without_bound_pass_gates_refuses_reservation(self):
        with patch.object(journal, "gate_snapshot", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "No SHA/path-bound PASS gate snapshot"):
                journal.reserve("business", self.article, "新稿")
        self.assertEqual(self.state, {})

    def test_mutated_archive_cannot_be_confirmed(self):
        journal.reserve("business", self.article, "新稿")
        self.article.write_text("# 被修改\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Archive modified"):
            journal.confirm("business", self.article, "media-123")

    def test_all_seven_publishers_reserve_before_wechat_post_and_confirm_after(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                s = (ROOT / profile / "publish_draft.py").read_text("utf-8")
                body = s.split("def create_draft(", 1)[1].split("\ndef main():", 1)[0]
                self.assertIn("reserve_draft_add", body)
                self.assertIn('"/draft/add"', body)
                self.assertIn("confirm_draft_add", body)
                self.assertLess(body.index("reserve_draft_add"), body.index('"/draft/add"'))
                self.assertLess(body.index('"/draft/add"'), body.index("confirm_draft_add"))
                workflow = (ROOT / ".github/workflows" / (profile + "-draft.yml")).read_text("utf-8")
                self.assertIn("CONTENT_OS_GITHUB_TOKEN: ${{ github.token }}", workflow)


if __name__ == "__main__":
    unittest.main()
