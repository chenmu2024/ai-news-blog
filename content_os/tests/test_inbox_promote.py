"""Offline verification of immutable inbox promotion."""
import json
import hashlib
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from content_os.inbox_promote import promote

DAY=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.candidate=self.root/"content_os"/"inbox"/"wechat"/f"{DAY}.md"
        self.sidecar=self.root/"content_os"/"inbox"/"wechat"/f"{DAY}.titles.json"
        self.candidate.parent.mkdir(parents=True)
        self.candidate.write_text('# 一家AI公司如何改善流程\n<!-- WECHAT_CARD {"title":"案例","items":[]} -->',"utf-8")
        self.rec={"candidates":["一家AI公司如何改善流程","一家AI创业公司怎样落地","一家新公司如何找到客户"],
            "selected_title":"一家AI公司如何改善流程",
            "rationale":"真实公司解决具体业务问题，事实核对且近30日标题不重复。",
            "basis":["官方项目主页","产品功能及用途","30日归档对照"],
            "verified_views":None,
            "evidence":{"facts_checked":True,"image_rights_checked":True,
                        "source_urls":["https://github.com/example/repo"]}}
        self.sidecar.write_text(json.dumps(self.rec,ensure_ascii=False),"utf-8")
        self.approval=self.root/"content_os"/"draft-approvals"/"wechat"/f"{DAY}.json"
        self.approval.parent.mkdir(parents=True)
        self.approval.write_text(json.dumps({
            "profile": "wechat", "article_id": DAY,
            "article_sha256": hashlib.sha256(self.candidate.read_bytes()).hexdigest(),
            "status": "approved", "approved_by": "user", "source": "chat",
            "approved_at": DAY + "T08:00:00+08:00",
            "user_confirmation": "同步草稿",
            "previewed_with_real_images": True,
        },ensure_ascii=False),"utf-8")
    def test_missing_daily_approval_must_not_create_archive(self):
        self.approval.unlink()
        result=promote(self.root,"wechat",DAY)
        if DAY >= "2026-10-15":
            self.assertEqual(result["status"],"FAIL",result)
            self.assertIn("multi_draft_missing_verified_user_approval_record",result["reasons"])
            self.assertFalse((self.root/"wechat"/"archive"/f"{DAY}.md").exists())

    def test_stale_daily_approval_must_not_create_archive(self):
        if DAY < "2026-10-15":
            self.skipTest("new rule only applies to future drafts")
        record=json.loads(self.approval.read_text("utf-8"))
        record["article_sha256"]="0"*64
        self.approval.write_text(json.dumps(record,ensure_ascii=False),"utf-8")
        result=promote(self.root,"wechat",DAY)
        self.assertEqual(result["status"],"FAIL",result)
        self.assertIn("multi_draft_approval_stale_body",result["reasons"])
        self.assertFalse((self.root/"wechat"/"archive"/f"{DAY}.md").exists())

    def test_disclosed_fiction_does_not_require_invented_fact_urls(self):
        if DAY < "2026-10-15":
            self.skipTest("purely fictional comics are enabled starting 2026-10-15")
        body="# 她关店时，门外还有一个人\\n\\n原创虚构漫画故事：一把伞改变了一次误会。\\n"
        body=body.replace("\\\\n","\\n")
        candidate=self.root/"content_os/inbox/business"/f"{DAY}.md"
        candidate.parent.mkdir(parents=True,exist_ok=True)
        candidate.write_text(body,encoding="utf-8")
        approval=self.root/"content_os/draft-approvals/business"/f"{DAY}.json"
        approval.parent.mkdir(parents=True,exist_ok=True)
        approval.write_text(json.dumps({
            "profile":"business","article_id":DAY,
            "article_sha256":hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "status":"approved","approved_by":"user","source":"chat",
            "approved_at":DAY+"T08:00:00+08:00",
            "user_confirmation":"同步草稿",
            "previewed_with_real_images":True
        },ensure_ascii=False),encoding="utf-8")
        title="她关店时，门外还有一个人"
        sidecar=candidate.with_suffix(".titles.json")
        sidecar.write_text(json.dumps({
            "candidates":[title,"雨夜小店门口的一个误会","把伞送回去的那个晚上"],
            "selected_title":title,
            "rationale":"原创暖心城市群像，明确虚构身份，不用伪造政务来源。",
            "basis":["真实故事与虚构情境明确分离"],
            "verified_views":None,
            "evidence":{"kind":"creative_fiction","no_external_factual_claims":True,
                        "source_urls":[],"facts_checked":True,"image_rights_checked":True}
        },ensure_ascii=False),encoding="utf-8")
        with patch("content_os.inbox_promote.validate",return_value={"status":"PASS","errors":[]}):
            result=promote(self.root,"business",DAY)
        self.assertEqual(result["status"],"READY_FOR_COMMIT",result)

    def test_fiction_does_not_suppress_actual_fact_source_requirements(self):
        if DAY < "2026-10-15":
            self.skipTest("new daily fiction route only")
        self.candidate.write_text(self.candidate.read_text("utf-8")+"原创虚构漫画故事\\n",encoding="utf-8")
        record=json.loads(self.approval.read_text("utf-8"))
        record["article_sha256"]=hashlib.sha256(self.candidate.read_bytes()).hexdigest()
        self.approval.write_text(json.dumps(record,ensure_ascii=False),encoding="utf-8")
        self.rec["evidence"]={"facts_checked":True,"image_rights_checked":True,"source_urls":[]}
        self.sidecar.write_text(json.dumps(self.rec,ensure_ascii=False),encoding="utf-8")
        result=promote(self.root,"wechat",DAY)
        self.assertIn("real_https_source_evidence_required",result["reasons"])

    def test_missing_candidate_skips(self):
        self.candidate.unlink()
        self.assertEqual(promote(self.root,"wechat",DAY)["status"],"SKIP")
    def test_invalid_title_prevents_archive(self):
        self.rec["selected_title"]="错误标题"
        self.sidecar.write_text(json.dumps(self.rec,ensure_ascii=False),"utf-8")
        self.assertEqual(promote(self.root,"wechat",DAY)["status"],"FAIL")
        self.assertFalse((self.root/"wechat/archive"/f"{DAY}.md").exists())
    def test_no_network_cannot_promote(self):
        self.assertEqual(promote(self.root,"wechat",DAY,check_network=False)["status"],"FAIL")
    def test_approved_candidate_stages_ledger_and_archive_only(self):
        with patch("content_os.inbox_promote.validate",return_value={"status":"PASS","errors":[]}):
            result=promote(self.root,"wechat",DAY)
        self.assertEqual(result["status"],"READY_FOR_COMMIT")
        self.assertTrue((self.root/"wechat/archive"/f"{DAY}.md").is_file())
        self.assertFalse((self.root/"wechat/status/latest.json").exists())
    def test_prior_archive_never_overwritten(self):
        file=self.root/"wechat/archive"/f"{DAY}.md"
        file.parent.mkdir(parents=True)
        file.write_text("untouched")
        self.assertEqual(promote(self.root,"wechat",DAY)["status"],"SKIP")
        self.assertEqual(file.read_text(),"untouched")

if __name__=="__main__":
    unittest.main()
