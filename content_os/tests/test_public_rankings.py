import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "content_os"))
import public_rankings as r

HTML_SAMPLE = '<h1>2026年10月6日</h1><h2>微信10万+爆款文章</h2>' + (
    '<a href="/a">01育儿教育的新问题查看标题拆解</a>'
    '<a href="/b">10一套懒人穿搭查看标题拆解</a>'
    '<a href="/c">30一家公司新的商业故事查看标题拆解</a>'
)

class RankingTests(unittest.TestCase):
    def test_identical_daily_lists_do_not_prove_recent_heat(self):
        def html_for_day(day):
            title = str(int(day[:4])) + "年" + str(int(day[5:7])) + "月" + str(int(day[8:10])) + "日"
            links = "".join('<a href="/article/{0}">{0:02d}近期育儿话题样本第{0}篇查看标题拆解</a>'.format(i)
                            for i in range(1, 13))
            return "<h1>" + title + "</h1><h2>微信10万+爆款文章</h2>" + links

        def fake_fetch(url):
            return html_for_day(url.rsplit("/", 1)[-1])

        report = r.find_public_rankings(fake_fetch, today=date(2026, 10, 8),
                                        window_days=2, max_successful_days=2)
        self.assertEqual(report["pages_found"], 2)
        self.assertEqual(report["freshness_status"], "suspected_repeated_snapshot")
        self.assertFalse(report["independent_recent_viral_evidence"])
        self.assertEqual(report["daily_overlap_checks"][0]["overlap_ratio"], 1.0)

    def test_one_ranked_day_is_not_independent_heat(self):
        def fake_fetch(url):
            if url.endswith("2026-10-06"):
                return HTML_SAMPLE
            raise ValueError("Unavailable")
        report = r.find_public_rankings(fake_fetch, today=date(2026, 10, 8),
                                        window_days=2, max_successful_days=1)
        self.assertEqual(report["freshness_status"], "unverifiable_single_day")
        self.assertFalse(report["independent_recent_viral_evidence"])

    def test_rank_and_provenance(self):
        rows = r.extract_rankings(HTML_SAMPLE, "2026-10-06", "https://weixinhost.com/hotspot-radar/2026-10-06")
        self.assertEqual([x["rank"] for x in rows], [1, 10, 30])
        self.assertTrue(all(x["article_read_count"] is None for x in rows))

    def test_date_validation(self):
        with self.assertRaises(ValueError):
            r.extract_rankings(HTML_SAMPLE, "2026-10-05", "https://weixinhost.com/hotspot-radar/2026-10-05")

    def test_repeated_headline_only_once(self):
        same = {"headline": "舒服到不想脱下来的一套懒人穿搭",
                "ranking_date": "2026-10-06", "rank": 6}
        newer = dict(same, ranking_date="2026-10-07")
        self.assertEqual(len(r.related_rankings("fashion", [same, newer])), 1)
        self.assertEqual(r.related_rankings("fashion", [same, newer])[0]["ranking_date"], "2026-10-07")

    def test_modern_sports_not_historical(self):
        modern_sports = [{"headline": "韩国男篮成绩历史第二差",
                          "ranking_date": "2026-10-07", "rank": 3}]
        self.assertEqual(r.related_rankings("zizhitongjian", modern_sports), [])

    def test_tv_plot_son_not_parenting(self):
        drama = [{"headline": "她生了儿子并被男主护住",
                  "ranking_date": "2026-10-07", "rank": 12}]
        self.assertEqual(r.related_rankings("parenting", drama), [])

    def test_topic_match(self):
        rows = r.extract_rankings(HTML_SAMPLE, "2026-10-06", "https://weixinhost.com/hotspot-radar/2026-10-06")
        self.assertEqual(len(r.related_rankings("fashion", rows)), 1)

if __name__ == "__main__":
    unittest.main()
