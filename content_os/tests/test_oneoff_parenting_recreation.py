"""Offline regression for the single consented, missing E draft recovery.

No network, external account, schedule, or mutation is involved in tests.
"""
import unittest

from content_os.oneoff_recreate_parenting_reviewed_20261013 import (
    scan, selected_articles, relevant_duplicate, NEW_TITLE, OLD_TITLE,
)


class OneOffParentingTests(unittest.TestCase):
    def test_recognize_revised_or_missing_original(self):
        for a in (
            {"title": OLD_TITLE, "content": ""},
            {"title": NEW_TITLE, "content": ""},
            {"title": "北京市育儿补贴办理", "content": "2026年首次申请可以提交"},
        ):
            self.assertTrue(relevant_duplicate(a))
        self.assertFalse(relevant_duplicate(
            {"title": "春天如何安排家庭预算", "content": "社保工资"}))

    def test_unrelated_drafts_and_no_publications_permits_preflight(self):
        calls = []
        def mock(endpoint, **kwargs):
            calls.append(endpoint)
            if endpoint == "/draft/batchget":
                return {"total_count": 1, "item": [{
                    "media_id": "unrelated",
                    "content": {"news_item": [{"title": "其他旧稿", "content": "其他内容"}]}}
                ]}
            if endpoint == "/freepublish/batchget":
                return {"total_count": 0, "item": []}
            raise AssertionError("Disallowed endpoint " + endpoint)
        out = scan(mock, {"access_token": "test"})
        self.assertEqual(out["/draft"]["count"], 1)
        self.assertEqual(out["/freepublish"]["count"], 0)
        self.assertEqual(set(calls), {"/draft/batchget", "/freepublish/batchget"})

    def test_duplicate_or_unbounded_scan_fails_closed(self):
        for kind in ("original", "revised", "related", "huge"):
            def fake(endpoint, **kwargs):
                if endpoint.startswith("/draft"):
                    if kind == "huge":
                        return {"total_count": 999}
                    article = {
                        "original": {"title": OLD_TITLE, "content": ""},
                        "revised": {"title": NEW_TITLE, "content": ""},
                        "related": {"title": "北京育儿补贴办理", "content": "补申请通道"},
                    }[kind]
                    return {"total_count": 1, "item": [{
                        "media_id": "old",
                        "content": {"news_item": [article]}}]}
                return {"total_count": 0, "item": []}
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, "refuse add|exhaustive"):
                scan(fake, {"access_token": "fake"})

    def test_malformed_page_fails_closed(self):
        def fake(endpoint, **kwargs):
            if endpoint.startswith("/draft"):
                return {"total_count": 1}
            return {"total_count": 0, "item": []}
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            scan(fake, {})

    def test_no_public_send_update_or_duplicate_retry_endpoints(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] /
                  "oneoff_recreate_parenting_reviewed_20261013.py").read_text("utf-8")
        for forbidden in ("/draft/update", "/freepublish/submit",
                          "/message/mass/send", "while True"):
            self.assertNotIn(forbidden, source)
        # The one single draft/add is gated by a committed remote receipt.
        self.assertLess(source.index("persist(github_token, repo, NEW_PATH, journal)"),
                        source.index('created = api("/draft/add"'))


if __name__ == "__main__":
    unittest.main()
