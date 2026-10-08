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

    def test_generic_wechat_login_is_not_an_article(self):
        self.assertFalse(m.is_useful_discovery({
            "title": "微信公众平台 - 微信公众平台",
            "url": "https://news.google.com/rss/articles/generic"}))
        self.assertTrue(m.is_useful_discovery({
            "title": "一个品牌被收购之后发生了什么",
            "url": "https://weixin.sogou.com/link?url=story"}))

    @patch.object(m, "wechat_results")
    @patch.object(m, "news_index_results")
    def test_insufficient_heat_uses_fact_based_writing_fallback(self, news, wechat):
        wechat.return_value = [
            {"title": "真正的独立开发故事", "url": "https://weixin.sogou.com/link?url=a",
             "heat_verified": False}]
        news.return_value = []
        info = m.scan("wechat")
        self.assertEqual(info["topic_gate"], "insufficient_evidence")
        self.assertEqual(info["writing_mode"], "fact_verified_source_fallback")
        self.assertTrue(info["writing_allowed"])
        self.assertEqual(info["heat_evidence_count"], 0)
        self.assertEqual(len(info["sources"]["wechat"]["attempts"]), 2)

    @patch.object(m, "wechat_results")
    @patch.object(m, "news_index_results")
    def test_full_primary_sample_skips_second_query(self, news, wechat):
        sample = [{"title": "完整可读的公众号标题" + str(i),
                   "url": "https://weixin.sogou.com/link?url=" + str(i),
                   "heat_verified": False} for i in range(5)]
        wechat.return_value = sample
        news.return_value = []
        info = m.scan("parenting")
        self.assertEqual(wechat.call_count, 1)
        self.assertEqual(info["sample_count"], 5)
        self.assertEqual(info["heat_evidence_count"], 0)

    @patch.object(m, "fetch")
    def test_rss_publication_date_is_not_assumed(self, fetch):
        fetch.return_value = ('<rss><channel><item><title>一篇真实文章标题</title>'
                              '<link>https://news.google.com/rss/articles/a</link>'
                              '<pubDate>Thu, 08 Oct 2026 00:00:00 GMT</pubDate>'
                              '</item></channel></rss>')
        row = m.news_index_results("AI")[0]
        self.assertIsNone(row["published_at"])
        self.assertEqual(row["indexed_at"], "Thu, 08 Oct 2026 00:00:00 GMT")
        self.assertFalse(row["heat_verified"])


if __name__ == "__main__":
    unittest.main()
