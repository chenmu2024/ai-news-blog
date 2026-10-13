"""Editorial approval is tied to exact work, never to a self-assigned score."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from content_os.editorial_review import check, policy_hash, review_path, CHECKS, HUMANIZER_STYLES


class EditorialReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.day = "2026-10-14"
        self.profile = "wechat"
        self.body = "# 一家公司的实际付费任务\n\n用户为了反复修改的工作付费，而不是只生成一次。\n\n调用费用并不是唯一成本，返工时间也需要计算。\n\n本文依据公开资料进行产品观察，没有声称真实测试过。\n"
        for name in ("PRODUCTION_BRIEF.md", "EDITORIAL_VOICE.md"):
            self.write("content_os/" + name, "Current production instructions\n")
        self.write("content_os/humanizer/README.md", "Humanizer V3 instructions\n")
        self.write("content_os/humanizer/account_profiles.json", "{}\n")
        self.write("content_os/humanizer/reference_manifest.json", "{}\n")
        self.write("content_os/editorial-feedback.json", json.dumps({"items": [
            {"id": "feedback-1", "active": True, "profiles": list(CHECKS)}]}))

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value.encode("utf-8"))

    def record(self, profile=None, body=None):
        profile = profile or self.profile
        body = body or self.body
        self.write(profile + "/STYLE.md", "Profile-specific style instructions\n")
        excerpt = body.split("\n\n")[1].strip()
        rec = {
            "schema_version": 1, "profile": profile, "date": self.day, "decision": "approve",
            "article_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "policy_sha256": policy_hash(self.root, profile),
            "reader": "已经准备开发配音工具的独立开发者",
            "question": "用户为什么愿意为反复修改的工作付费",
            "new_information": "把失败返工的成本放进同一个任务观察",
            "topic_key": "voice-revision-workflow-" + profile,
            "rejected_topics": [{"question": "这家公司的总收入有多少", "reason": "没有公开可靠的收入核验依据"},
                                {"question": "哪一个语音模型听起来最好", "reason": "没有同条件的实际试听比较材料"}],
            "evidence": [{"url": "https://example.org/primary", "claim": "产品为可反复编辑的工作提供功能", "article_excerpt": excerpt}],
            "history": [], "profile_checks": {name: excerpt for name in CHECKS[profile]},
            "reader_review": {"finding": "原稿只有功能罗列没有具体任务", "change": "删去重复建议并明确本篇分析范围", "final_excerpt": excerpt, "unresolved": []},
            "fact_review": {"finding": "原稿把资料观察误写成实际测试", "change": "明确没有做实测并核对公开产品资料", "final_excerpt": excerpt, "unresolved": []},
            "humanizer": {
                "version": "v3",
                "reference_library": "wechat-humanizer-v3-2014-2016",
                "reference_examples": [
                    {"origin": "project_bank", "reference_id": "project:001", "source_name": "来源甲",
                     "style": sorted(HUMANIZER_STYLES[profile])[0], "learned_feature": "学习自然开头和不等长段落"},
                    {"origin": "project_bank", "reference_id": "project:002", "source_name": "来源乙",
                     "style": sorted(HUMANIZER_STYLES[profile])[0], "learned_feature": "学习具体细节先于抽象总结"},
                    {"origin": "web_benchmark", "reference_id": "web:003", "source_name": "来源丙",
                     "style": sorted(HUMANIZER_STYLES[profile])[0], "learned_feature": "学习克制结尾与作者判断",
                     "url": "https://example.org/benchmark"}
                ],
                "anti_patterns_removed": ["删除机械总结", "打破等长段落"],
                "final_excerpt": excerpt,
                "copied_reference_text": False,
                "fact_recheck": True
            },
            "feedback_applied": [{"id": "feedback-1", "change": "删去泛化建议，用一个任务支撑正文判断"}],
        }
        return rec

    def save(self, rec):
        path = review_path(self.root, rec["profile"], self.day)
        self.write(path.relative_to(self.root), json.dumps(rec, ensure_ascii=False))

    def test_historical_articles_do_not_require_new_records(self):
        self.assertEqual(check(self.root, "wechat", "2026-10-13", self.body)["status"], "NOT_REQUIRED")

    def test_missing_review_fails(self):
        self.assertEqual(check(self.root, "wechat", self.day, self.body)["status"], "FAIL")

    def test_complete_review_passes_for_every_profile(self):
        for profile in CHECKS:
            with self.subTest(profile=profile):
                body = self.body
                if profile == "fashion":
                    body += "\n".join(f"![图{i}](https://example.org/{i}.jpg)\n\n第{i}张照片的外套下摆和裤腰形成不同的可见关系。" for i in range(5))
                rec = self.record(profile, body)
                if profile == "fashion":
                    rec["profile_checks"]["photo_analysis"] = [
                        {"image_url": f"https://example.org/{i}.jpg", "article_excerpt": f"第{i}张照片的外套下摆和裤腰形成不同的可见关系。"} for i in range(5)]
                self.save(rec)
                self.assertEqual(check(self.root, profile, self.day, body)["errors"], [])

    def test_review_cannot_be_reused_after_body_changes(self):
        self.save(self.record())
        self.assertIn("editorial_review_stale_article", check(self.root, "wechat", self.day, self.body + "新内容")["errors"])

    def test_policy_change_requires_new_review(self):
        self.save(self.record())
        self.write("content_os/PRODUCTION_BRIEF.md", "Changed instructions\n")
        self.assertIn("editorial_review_stale_policy", check(self.root, "wechat", self.day, self.body)["errors"])

    def test_policy_hash_is_portable_across_checkout_line_endings(self):
        rec = self.record()
        self.write("content_os/PRODUCTION_BRIEF.md", "Current production instructions\r\n")
        self.assertEqual(rec["policy_sha256"], policy_hash(self.root, "wechat"))

    def test_fashion_rejects_reused_photo_analysis_and_invalid_image_key(self):
        body = self.body + "\n".join(f"![图{i}](https://example.org/{i}.jpg)" for i in range(5))
        rec = self.record("fashion", body)
        excerpt = self.body.split("\n\n")[1].strip()
        rec["profile_checks"]["photo_analysis"] = [
            {"image_url": f"https://example.org/{i}.jpg", "article_excerpt": excerpt} for i in range(5)]
        self.save(rec)
        self.assertIn("editorial_fashion_analysis_missing_or_reused", check(self.root, "fashion", self.day, body)["errors"])
        rec["profile_checks"]["photo_analysis"][0]["image_url"] = []
        self.save(rec)
        self.assertEqual(check(self.root, "fashion", self.day, body)["status"], "FAIL")

    def test_revise_and_unresolved_are_not_approved(self):
        rec = self.record()
        rec["decision"] = "revise"
        rec["fact_review"]["unresolved"] = ["费用仍然没有来源"]
        self.save(rec)
        errors = check(self.root, "wechat", self.day, self.body)["errors"]
        self.assertIn("editorial_incomplete_fact_review", errors)
        self.assertIn("editorial_review_not_approved_for_profile_and_date", errors)

    def test_generic_evidence_absent_from_body_is_rejected(self):
        rec = self.record()
        rec["profile_checks"]["paid_task"] = "这段根本没有出现在最后的正文里面"
        rec["evidence"][0]["article_excerpt"] = "我已全面核验所有相关内容与来源"
        rec["feedback_applied"] = []
        self.save(rec)
        errors = check(self.root, "wechat", self.day, self.body)["errors"]
        self.assertIn("editorial_source_evidence_invalid", errors)
        self.assertIn("editorial_profile_evidence_missing:paid_task", errors)
        self.assertIn("editorial_feedback_not_addressed:feedback-1", errors)

    def test_recent_archive_needs_substantive_comparison(self):
        self.write("wechat/archive/2026-10-13.md", "# 上一次不同的题目\n")
        rec = self.record()
        self.save(rec)
        self.assertIn("editorial_recent_history_comparison_missing", check(self.root, "wechat", self.day, self.body)["errors"])
        rec["history"] = [{"path": "wechat/archive/2026-10-13.md", "difference": "上次只谈付费档位，本次核对返工任务成本"}]
        self.save(rec)
        self.assertEqual(check(self.root, "wechat", self.day, self.body)["status"], "PASS")

    def test_cross_account_policy_topic_duplicate_is_rejected(self):
        rec = self.record("business")
        self.save(rec)
        other = self.record("parenting")
        other["topic_key"] = rec["topic_key"]
        self.save(other)
        self.assertIn("editorial_repeated_topic_key", check(self.root, "parenting", self.day, self.body)["errors"])

    def test_observational_life_essay_does_not_need_irrelevant_authority(self):
        rec = self.record("jingyun")
        rec["evidence"][0].update(kind="observation", url=None)
        self.save(rec)
        self.assertEqual(check(self.root, "jingyun", self.day, self.body)["status"], "PASS")

    def test_missing_review_blocks_archive_and_draft_before_remote_writes(self):
        from content_os.prearchive_validate import static_check
        result = static_check(self.root, "wechat", self.day, self.body)
        self.assertTrue(any("editorial_review" in x for x in result["errors"]))
        article = self.root / "wechat/archive" / (self.day + ".md")
        self.write(article.relative_to(self.root), self.body)
        from content_os.draft_preflight import inspect
        with self.assertRaisesRegex(ValueError, "Editorial review"):
            inspect(article, "wechat", self.root / "wechat/status")
        from content_os.draft_journal import reserve
        with patch("content_os.draft_journal._environment") as remote:
            with self.assertRaisesRegex(RuntimeError, "Editorial review"):
                reserve("wechat", article, "一家公司的实际付费任务")
            remote.assert_not_called()

    def test_health_reports_missing_editorial_proof(self):
        self.write("wechat/archive/2026-10-14.md", self.body)
        from content_os.daily_healthcheck import audit_profile
        result = audit_profile(self.root, "wechat", self.day)
        self.assertEqual(result["editorial_review"]["status"], "FAIL")

    def test_hidden_metadata_never_counts_as_article_or_fact_signal(self):
        from content_os.quality_gate import strip_production_markup
        self.assertEqual(strip_production_markup('# 正文\n<!-- AI_SCENE {"description":"2026年 API 300万元"} -->'), "正文")


if __name__ == "__main__":
    unittest.main()
