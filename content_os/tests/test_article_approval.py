"""Approval regression: new daily and extra articles are fail-closed; old archives stay immutable."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from content_os.multi_draft import verify_article_approval


class ArticleApprovalTests(unittest.TestCase):
    BODY = "# 一份待审的原创漫画\n\n这是待审正文。\n"
    DAY = "2026-10-15"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def approval(self, profile="business", article_id=DAY, body=BODY):
        path = self.root/"content_os"/"draft-approvals"/profile/(article_id+".json")
        path.parent.mkdir(parents=True,exist_ok=True)
        data = {
            "profile": profile, "article_id": article_id,
            "article_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "status": "approved", "approved_by": "user", "source": "chat",
            "approved_at": "2026-10-15T08:12:00+08:00",
            "user_confirmation": "同步草稿",
            "previewed_with_real_images": True
        }
        path.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
        return path

    def test_new_daily_missing_approval_is_blocked(self):
        self.assertIn("multi_draft_missing_verified_user_approval_record",
                      verify_article_approval(self.root,"business",self.DAY,self.BODY))

    def test_new_daily_exact_chat_approval_is_accepted(self):
        self.approval()
        self.assertEqual(verify_article_approval(self.root,"business",self.DAY,self.BODY),[])

    def test_new_daily_changed_body_is_rejected(self):
        self.approval()
        self.assertIn("multi_draft_approval_stale_body",
                      verify_article_approval(self.root,"business",self.DAY,self.BODY+"篡改"))

    def test_missing_explicit_user_text_is_rejected(self):
        path=self.approval()
        data=json.loads(path.read_text("utf-8"))
        data["user_confirmation"]="修复"
        path.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
        self.assertIn("multi_draft_explicit_user_permission_missing",
                      verify_article_approval(self.root,"business",self.DAY,self.BODY))

    def test_legacy_daily_does_not_require_retroactive_approval(self):
        self.assertEqual(verify_article_approval(self.root,"business","2026-10-14",self.BODY),[])

    def test_new_extra_also_requires_independent_approval(self):
        extra=self.DAY+"--second-story"
        self.assertIn("multi_draft_missing_verified_user_approval_record",
                      verify_article_approval(self.root,"business",extra,self.BODY))
        self.approval(article_id=extra)
        self.assertEqual(verify_article_approval(self.root,"business",extra,self.BODY),[])


if __name__ == "__main__":
    unittest.main()
