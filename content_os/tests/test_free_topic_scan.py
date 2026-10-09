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

    def test_login_page_and_explicit_old_year_are_not_current_stories(self):
        self.assertFalse(m.is_useful_discovery({
            "title": "Weixin - 微信公众平台 - 微信公众平台",
            "url": "https://weixin.qq.com/login"
        }))
        self.assertFalse(m.is_useful_discovery({
            "title": "2023年度消费品牌TOP100 瑞幸增长榜单",
            "url": "https://weixin.sogou.com/link?url=old"
        }))
        self.assertTrue(m.is_useful_discovery({
            "title": "瑞幸咖啡近期开店的商业逻辑",
            "url": "https://weixin.sogou.com/link?url=new"
        }))

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


    @patch.object(m, "bing_news_results")
    @patch.object(m, "wechat_results")
    @patch.object(m, "news_index_results")
    def test_public_news_backup_never_becomes_wechat_popularity(self, google, wechat, bing):
        wechat.side_effect = OSError("public index down")
        google.return_value = []
        bing.return_value = [{
            "title": "一家真实公司发布了新的公告",
            "url": "https://example.com/report",
            "platform": "bing_news_rss_non_wechat", "heat_verified": False,
            "reference_only": True
        }]
        result = m.scan("business", use_extra_public_fallback=True)
        self.assertEqual(result["sample_count"], 0)
        self.assertEqual(result["heat_evidence_count"], 0)
        self.assertEqual(result["topic_gate"], "insufficient_evidence")
        self.assertTrue(result["writing_allowed"])
        self.assertEqual(result["fallback_news_count"], 1)
        self.assertEqual(result["sources"]["bing_news_fallback"]["status"], "ok")

    @patch.object(m, "general_news_results")
    @patch.object(m, "bing_news_results")
    @patch.object(m, "wechat_results")
    @patch.object(m, "news_index_results")
    def test_all_sources_failing_still_allows_fact_based_writing(self, google, wechat, bing, general):
        wechat.side_effect = OSError("unavailable")
        google.side_effect = OSError("unavailable")
        bing.side_effect = OSError("unavailable")
        general.side_effect = OSError("unavailable")
        result = m.scan("parenting", use_extra_public_fallback=True)
        self.assertEqual(result["sample_count"], 0)
        self.assertEqual(result["fallback_news_count"], 0)
        self.assertEqual(result["topic_gate"], "insufficient_evidence")
        self.assertTrue(result["writing_allowed"])
        self.assertEqual(result["sources"]["bing_news_fallback"]["status"], "error")

    @patch.object(m, "bing_news_results")
    @patch.object(m, "wechat_results")
    @patch.object(m, "news_index_results")
    def test_full_wechat_sample_without_heat_still_adds_news_signal(self, google, wechat, bing):
        wechat.return_value = [{"title": "真实公众号候选标题编号" + str(i),
                                "url": "https://weixin.sogou.com/link?q=" + str(i),
                                "heat_verified": False} for i in range(5)]
        google.return_value = []
        bing.return_value = [{"title": "公开来源报道新企业事件",
                              "url": "https://example.com/news",
                              "heat_verified": False}]
        result = m.scan("business", use_extra_public_fallback=True)
        self.assertEqual(result["sample_count"], 5)
        self.assertEqual(result["fallback_news_count"], 1)
        self.assertEqual(result["heat_evidence_count"], 0)

    @patch.object(m, "fetch")
    def test_bing_rss_is_reference_only(self, fetch):
        fetch.return_value = ('<rss><channel><item>'
                              '<title>一家企业宣布新产品功能</title>'
                              '<link>https://example.com/news/story</link>'
                              '<pubDate>Fri, 09 Oct 2026 00:00:00 GMT</pubDate>'
                              '</item></channel></rss>')
        items = m.bing_news_results("企业 AI")
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["reference_only"])
        self.assertFalse(items[0]["heat_verified"])
        self.assertIsNone(items[0]["published_at"])
        self.assertIn("not a WeChat original", items[0]["verification"])


    def test_same_day_cache_is_only_labeled_reference_not_false_success(self):
        old = {"local_date": "2026-10-09", "generated_at": "2026-10-09T06:10:00+08:00",
               "profiles": {"fashion": {"articles": [{
                   "title": "来自早晨扫描的真实穿搭标题",
                   "url": "https://weixin.sogou.com/link?url=story"
               }]}}}
        report = {"profiles": {"fashion": {
            "sample_count": 0, "heat_evidence_count": 0,
            "fallback_news_count": 0, "sources": {},
            "topic_gate": "insufficient_evidence"
        }}}
        m.attach_fallback_references(report, old, "2026-10-09")
        obj = report["profiles"]["fashion"]
        self.assertEqual(obj["sample_count"], 0)
        self.assertEqual(obj["heat_evidence_count"], 0)
        self.assertEqual(len(obj["same_day_cached_references"]), 1)
        self.assertEqual(obj["sources"]["same_day_cache"]["status"],
                         "cached_earlier_today_not_new_fetch")

    def test_yesterday_cache_remains_historical(self):
        old = {"local_date": "2026-10-08", "profiles": {"fashion": {
            "articles": [{"title": "旧日穿搭文章线索",
                          "url": "https://weixin.sogou.com/link?url=yesterday"}]}}}
        report = {"profiles": {"fashion": {
            "sample_count": 0, "heat_evidence_count": 0,
            "fallback_news_count": 0, "sources": {}
        }}}
        m.attach_fallback_references(report, old, "2026-10-09")
        item = report["profiles"]["fashion"]
        self.assertNotIn("same_day_cached_references", item)
        self.assertEqual(item["prior_reference_date"], "2026-10-08")
        self.assertEqual(item["sample_count"], 0)


if __name__ == "__main__":
    unittest.main()
