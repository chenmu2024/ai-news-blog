"""Offline contract tests: no WeChat write API calls and no external network."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from content_os.public_draft_contract import (
    image_sources, strip_figure_captions, verify_saved_payload, verify_and_record,
)

def body(count=1):
    return "<section>" + "".join(
        f'<p><img src="https://mmbiz.qpic.cn/mmbiz_jpg/uniqueid{i}/0" /></p>'
        for i in range(count)) + "</section>"

class PublicBodyTests(unittest.TestCase):
    def test_six_accounts_no_caption_and_prose_preserved(self):
        input_md = ("# 标题\n\n![场景](https://example.org/a.jpg)\n\n"
                    "*AI原创写实示意图：一间办公室*\n\n下一段正文保留。\n")
        for p in ("qiezhi", "wechat", "business", "zizhitongjian", "parenting", "jingyun"):
            result = strip_figure_captions(input_md, p)
            self.assertNotIn("AI原创写实示意图", result)
            self.assertIn("下一段正文保留", result)
            self.assertIn("![场景]", result)
        self.assertEqual(strip_figure_captions(input_md, "fashion"), input_md)

    def test_non_caption_text_stays(self):
        original = "![a](https://a.net/1.jpg)\n\n文章接着讨论事实。\n"
        self.assertEqual(strip_figure_captions(original, "business"), original)

    def test_success_and_invalid_payloads(self):
        html = body(2)
        payload = {"news_item": [{"title": "标题", "content": html}]}
        self.assertEqual(verify_saved_payload("wechat", "标题", "mid", html, payload)
                         ["inline_image_count"], 2)
        for candidate in (body(1), html + " AI_SCENE", html + " AI原创写实示意图"):
            with self.subTest(candidate=candidate[-30:]):
                with self.assertRaises(RuntimeError):
                    verify_saved_payload("wechat", "标题", "mid", html,
                                         {"news_item": [{"title": "标题", "content": candidate}]})

    def test_fashion_five_distinct(self):
        html = body(5)
        repeated = '<img src="https://mmbiz.qpic.cn/mmbiz_jpg/uniqueid0/0"/>' * 5
        with self.assertRaises(RuntimeError):
            verify_saved_payload("fashion", "标题", "mid", html,
                                 {"news_item": [{"title": "标题", "content": repeated}]})

    def test_verify_calls_only_draft_get(self):
        with tempfile.TemporaryDirectory() as root:
            article = Path(root) / "wechat/archive/2026-10-13.md"
            article.parent.mkdir(parents=True)
            article.write_text("# 标题\n", "utf-8")
            req = Mock()
            req.return_value.json.return_value = {"news_item": [{"title": "标题", "content": body()}]}
            cwd = Path.cwd()
            import os
            try:
                os.chdir(root)
                report = verify_and_record("wechat", Path("wechat/archive/2026-10-13.md"),
                                           "标题", "mid", body(), "token", req,
                                           "https://api.weixin.qq.com/cgi-bin")
                self.assertTrue(report["draft_get_verified"])
                self.assertTrue(req.call_args.args[1].endswith("/draft/get"))
                self.assertTrue(Path("wechat/status/draft-readback/2026-10-13.json").exists())
            finally:
                os.chdir(cwd)

    def test_visual_gate_fallback_is_persisted_for_existing_workflows(self):
        import hashlib
        import json
        import os
        with tempfile.TemporaryDirectory() as root:
            cwd = Path.cwd()
            try:
                os.chdir(root)
                article = Path("business/archive/2026-10-13.md")
                article.parent.mkdir(parents=True)
                article.write_text("# 标题\n", "utf-8")
                sha = hashlib.sha256(article.read_bytes()).hexdigest()
                gate = Path("business/status/visual-gate.json")
                gate.parent.mkdir(parents=True)
                gate.write_text(json.dumps({
                    "status": "PASS", "article_path": article.as_posix(),
                    "article_sha256": sha,
                }), "utf-8")
                call = Mock()
                call.return_value.json.return_value = {
                    "news_item": [{"title": "标题", "content": body()}]}
                verify_and_record("business", article, "标题", "mid",
                                  body(), "tok", call, "https://api.weixin.qq.com/cgi-bin")
                recorded = json.loads(gate.read_text("utf-8"))
                self.assertEqual(recorded["wechat_inline_readback"]["draft_media_id"], "mid")
                self.assertEqual(recorded["wechat_inline_readback"]["article_sha256"], sha)
                gate.write_text(json.dumps({
                    "status": "PASS", "article_path": article.as_posix(),
                    "article_sha256": "0" * 64
                }), "utf-8")
                with self.assertRaisesRegex(RuntimeError, "binding"):
                    verify_and_record("business", article, "标题", "mid",
                                      body(), "tok", call, "https://api.weixin.qq.com/cgi-bin")
            finally:
                os.chdir(cwd)

    def test_publishers_have_no_mass_send_or_publication_api(self):
        root = Path(__file__).resolve().parents[2]
        for p in ("qiezhi", "wechat", "business", "zizhitongjian",
                  "parenting", "jingyun", "fashion"):
            text = (root / p / "publish_draft.py").read_text("utf-8")
            for forbidden in ("/freepublish/submit", "/message/mass/send",
                              "/message/mass/sendall"):
                self.assertNotIn(forbidden, text)

if __name__ == "__main__":
    unittest.main()
