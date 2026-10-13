"""Pre-archive checks are immutable, date-aware, and safe without network."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prearchive_validate import static_check, fashion_evergreen_star_repeat

class CandidateValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.day = "2026-10-11"

    def test_draft_with_valid_cards_can_start_without_fresh_scan(self):
        md = '# 一家AI公司转型背后的生意选择\n' + '<!-- WECHAT_CARD {"title":"分析","items":[]} -->'
        self.assertEqual(static_check(self.root,"wechat",self.day,md)["status"],"PASS")

    def test_existing_archive_is_immutable(self):
        archive = self.root / 'wechat/archive/2026-10-11.md'
        archive.parent.mkdir(parents=True)
        archive.write_text('# 旧稿',encoding='utf-8')
        md = '# 一家AI公司转型背后的生意选择\n' + '<!-- WECHAT_CARD {"title":"分析","items":[]} -->'
        self.assertIn("today_archive_already_exists_never_overwrite",
                      static_check(self.root,"wechat",self.day,md)["errors"])

    def test_attempted_draft_must_block(self):
        journal = self.root / "wechat/status/draft-attempts/2026-10-11.json"
        journal.parent.mkdir(parents=True)
        journal.write_text('{"state":"attempted"}',encoding='utf-8')
        md = '# 一家AI公司转型背后的生意选择\n' + '<!-- WECHAT_CARD {"title":"分析","items":[]} -->'
        self.assertIn("draft_add_attempt_journal_present_manual_review_only",
                      static_check(self.root,"wechat",self.day,md)["errors"])

    def test_every_profile_checks_prior_30day_duplicate(self):
        archive = self.root / "jingyun/archive/2026-10-10.md"
        archive.parent.mkdir(parents=True)
        archive.write_text('# 中年女性重新找工作\n',encoding='utf-8')
        md = '# 中年女性重新找工作\n![Scene](https://images.example.com/a.jpg)'
        self.assertIn("30day_exact_duplicate_title",
                      static_check(self.root,"jingyun",self.day,md)["errors"])

    def test_fashion_same_star_repeat_blocks_changed_title(self):
        folder = self.root / "fashion/archive"
        folder.mkdir(parents=True)
        (folder/"2026-10-11.md").write_text(
            "# Jisoo五套经典造型，普通人最该学哪一招\n",encoding="utf-8")
        self.assertTrue(fashion_evergreen_star_repeat(
            folder,"2026-10-13","Jisoo五张旧照：领口比同款更值得抄"))
        self.assertFalse(fashion_evergreen_star_repeat(
            folder,"2026-10-13","Sana五次公开亮相，哪些衣服值得照搬"))
        self.assertFalse(fashion_evergreen_star_repeat(
            folder,"2026-10-13","Jisoo今日发布新的具体活动通告"))

    def test_fashion_missing_rights_is_blocked(self):
        manifest = {"topic_type":"celebrity","subject":"Jisoo",
                    "images":[{"image_url":f"https://photos.example.org/{i}.jpg",
                               "verified":True,"rights":"","source_page_url":""}
                              for i in range(5)]}
        md = '<!-- FASHION_SOURCE\n'+json.dumps(manifest,ensure_ascii=False)+'\n-->\n# Jisoo机场穿搭\n'
        md += '\n'.join(f'![Image {i}](https://photos.example.org/{i}.jpg)' for i in range(5))
        self.assertIn("fashion: unverified rights/source on photo 1",
                      static_check(self.root,"fashion",self.day,md)["errors"])

if __name__ == "__main__":
    unittest.main()
