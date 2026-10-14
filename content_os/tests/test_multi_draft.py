"""Offline regression for safe N-per-day WeChat draft identities."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from content_os.multi_draft import (
    get_article_identity, validate_article_id, verify_extra_approval,
)
from content_os.draft_preflight import inspect
from content_os.draft_journal import journal_path
from content_os.inbox_promote import promote
from content_os.prearchive_validate import static_check

DAY="2026-10-15"
ID1=DAY+"--comic-test-01"
ID2=DAY+"--comic-test-02"

class MultiDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.profile="jingyun"
        self.folder=self.root/self.profile/"archive"
        self.folder.mkdir(parents=True)
        self.first=self.folder/(DAY+".md")
        self.first.write_text("# 日更旧稿\n\n既有正文","utf-8")
        self.second=self.folder/(ID1+".md")
        self.second.write_text("# 结婚九年，我们开始用便签说话\n\n虚构原创关系漫画","utf-8")
    def approved(self,article,body=None):
        body=body or article.read_text("utf-8")
        file=self.root/"content_os"/"draft-approvals"/self.profile/(article.stem+".json")
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(json.dumps({
            "profile":self.profile,"article_id":article.stem,
            "article_sha256":hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "status":"approved","approved_by":"user","source":"chat",
            "approved_at":"2026-10-15T08:00:00+08:00",
            "user_confirmation":"创建微信草稿",
            "previewed_with_real_images":True
        },ensure_ascii=False),"utf-8")
    def test_identities_and_unsafe_paths(self):
        self.assertEqual(get_article_identity(self.first,self.profile),(DAY,DAY))
        self.assertEqual(get_article_identity(self.second,self.profile),(DAY,ID1))
        for bad in (DAY+"--", DAY+"--UPPER", DAY+"--../bad",DAY+"--bad-", DAY+"--a/b"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_article_id(DAY,bad)
    def test_one_existing_date_does_not_block_additional_distinct_article(self):
        self.approved(self.second)
        with patch("content_os.prearchive_validate.publisher_check",return_value={"status":"PASS","errors":[]}),\
             patch("content_os.editorial_review.check",return_value={"status":"PASS","errors":[]}),\
             patch("content_os.prearchive_validate.assess_editorial_title",return_value={"status":"PASS","reasons":[]}):
            result=static_check(self.root,self.profile,DAY,self.second.read_text("utf-8"),article_id=ID1)
        # Only the SAME supplementary ID blocks; the daily file does not.
        self.assertEqual(result["errors"],["today_archive_already_exists_never_overwrite"])
        # Existing same-ID immutable archive must block, but existing daily alone does not.
        self.assertEqual(result["status"],"FAIL")
        self.assertEqual(result["errors"],["today_archive_already_exists_never_overwrite"])
    def test_independent_wip_candidate_not_blocked_by_existing_daily_receipt(self):
        candidate=self.second.with_name(ID2+".md")
        self.approved(candidate,"# 另一篇漫画\n\n不同的文章")
        status=self.root/self.profile/"status/latest.json"
        status.parent.mkdir(parents=True)
        status.write_text(json.dumps({"status":"success","article_path":f"jingyun/archive/{DAY}.md"}),"utf-8")
        with patch("content_os.prearchive_validate.publisher_check",return_value={"status":"PASS","errors":[]}),\
             patch("content_os.editorial_review.check",return_value={"status":"PASS","errors":[]}),\
             patch("content_os.prearchive_validate.assess_editorial_title",return_value={"status":"PASS","reasons":[]}):
            result=static_check(self.root,self.profile,DAY,"# 另一篇漫画\n\n不同的文章",article_id=ID2)
        self.assertEqual(result["status"],"PASS",result["errors"])
        self.assertTrue(self.first.is_file())
    def test_extra_requires_exact_user_approval_bound_to_content(self):
        self.assertIn("multi_draft_missing_verified_user_approval_record",
                      verify_extra_approval(self.root,self.profile,ID1,self.second.read_text("utf-8")))
        self.approved(self.second)
        self.assertEqual(verify_extra_approval(self.root,self.profile,ID1,self.second.read_text("utf-8")),[])
        self.assertIn("multi_draft_approval_stale_body",
                      verify_extra_approval(self.root,self.profile,ID1,"不同内容"))
    def test_journals_are_per_article_not_per_day(self):
        self.assertNotEqual(journal_path(self.profile,self.first),journal_path(self.profile,self.second))
        self.assertTrue(journal_path(self.profile,self.second).endswith(ID1+".json"))
    def test_existing_daily_receipt_does_not_stop_extra_preflight(self):
        self.approved(self.second)
        state=self.root/self.profile/"status/latest.json"
        state.parent.mkdir(parents=True)
        daily=hashlib.sha256(self.first.read_bytes()).hexdigest()
        state.write_text(json.dumps({"status":"success","article_path":f"jingyun/archive/{DAY}.md",
                    "article_sha256":daily,"title":"日更旧稿"}),"utf-8")
        with patch("content_os.editorial_review.check",return_value={"status":"PASS","errors":[]}):
            result=inspect(self.second,self.profile)
        self.assertTrue(result["should_publish"])
    def test_inbox_promotion_independent_id_and_ledger(self):
        source=self.root/"content_os/inbox"/self.profile/(ID2+".md")
        source.parent.mkdir(parents=True,exist_ok=True)
        text="# 额外一篇新稿\n\n虚构关系漫画情景"
        source.write_text(text,"utf-8")
        self.approved(source,text)
        side=source.with_suffix(".titles.json")
        side.write_text(json.dumps({"selected_title":"额外一篇新稿",
             "candidates":["额外一篇新稿","备选标题一","备选标题二"],
             "verified_views":None,
             "evidence":{"facts_checked":True,"image_rights_checked":True,
                         "source_urls":["https://example.com/policy"]}}),"utf-8")
        with patch("content_os.inbox_promote.validate_record",return_value=[]),\
             patch("content_os.inbox_promote.validate",return_value={"status":"PASS","errors":[]}):
            result=promote(self.root,self.profile,DAY,article_id=ID2)
        # Date must be today for actual promotion; guard ensures stale dates do not publish.
        from datetime import datetime
        from zoneinfo import ZoneInfo
        if datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()==DAY:
            self.assertEqual(result["status"],"READY_FOR_COMMIT",result)
            self.assertTrue((self.folder/(ID2+".md")).exists())
            self.assertTrue((self.root/"content_os/title-decisions"/(ID2+".json")).exists())
        else:
            self.assertEqual(result["status"],"SKIP")
    def test_legacy_daily_workflow_resolver_does_not_pick_additional(self):
        for profile in ("qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion"):
            script=(Path(__file__).resolve().parents[2]/".github/workflows"/(profile+"-draft.yml")).read_text("utf-8")
            self.assertIn("-name '????-??-??.md'",script)
        extra=(Path(__file__).resolve().parents[2]/".github/workflows/multi-draft-bridge.yml").read_text("utf-8")
        self.assertIn("draft_preflight.py",extra)
        self.assertIn("draft-readback",extra)
        self.assertNotIn('cp "$ARTICLE_PATH" jingyun/articles/today.md',extra)

if __name__=="__main__":unittest.main()
