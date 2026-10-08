import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "content_os"))
import public_rankings as r

HTML_SAMPLE = '<h1>2026年10月6日</h1><h2>微信10万+爆款文章</h2>' + (
    '<a href="/a">01育儿教育的新问题查看标题拆解</a>'
    '<a href="/b">10一套懒人穿搭查看标题拆解</a>'
    '<a href="/c">30一家公司新的商业故事查看标题拆解</a>'
)

class RankingTests(unittest.TestCase):
    def test_rank_and_provenance(self):
        rows = r.extract_rankings(HTML_SAMPLE, "2026-10-06", "https://weixinhost.com/hotspot-radar/2026-10-06")
        self.assertEqual([x["rank"] for x in rows], [1, 10, 30])
        self.assertTrue(all(x["article_read_count"] is None for x in rows))

    def test_date_validation(self):
        with self.assertRaises(ValueError):
            r.extract_rankings(HTML_SAMPLE, "2026-10-05", "https://weixinhost.com/hotspot-radar/2026-10-05")

    def test_topic_match(self):
        rows = r.extract_rankings(HTML_SAMPLE, "2026-10-06", "https://weixinhost.com/hotspot-radar/2026-10-06")
        self.assertEqual(len(r.related_rankings("fashion", rows)), 1)

if __name__ == "__main__":
    unittest.main()
