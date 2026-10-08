import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "content_os"))
import free_topic_scan as m


class TopicScanTests(unittest.TestCase):
    def test_exact_wechat_heading_anchor_capture(self):
        p = m.WechatAnchorParser()
        p.feed('<div><a href="https://example.com">Other</a>'
               '<h3><a href="/link?url=x"><em>AI</em> 商业故事与机会</a></h3></div>')
        self.assertEqual(len(p.articles), 1)
        self.assertIn("商业故事", p.articles[0]["title"])
        self.assertIsNone(p.articles[0]["heat"])

    @patch.object(m, "wechat_results")
    @patch.object(m, "news_index_results")
    def test_no_fabricated_heat(self, news, wechat):
        wechat.return_value = [{"title": "A", "url": "https://weixin.sogou.com/link?id=1",
                                "platform": "sogou", "heat_verified": False}]
        news.return_value = []
        result = m.scan("wechat")
        self.assertEqual(result["topic_gate"], "insufficient_evidence")
        self.assertEqual(result["heat_evidence_count"], 0)

    @patch.object(m, "wechat_results")
    @patch.object(m, "news_index_results")
    def test_error_does_not_mask_other_source(self, news, wechat):
        wechat.side_effect = ValueError("CAPTCHA")
        news.return_value = []
        result = m.scan("fashion")
        self.assertEqual(result["sources"]["wechat"]["status"], "error")
        self.assertEqual(result["topic_gate"], "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
