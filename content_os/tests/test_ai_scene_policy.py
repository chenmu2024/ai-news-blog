"""Offline regression for mandatory original AI realism illustrations."""
from __future__ import annotations
import hashlib
import unittest
from content_os.ai_scene_policy import check, verify_bytes
from content_os.publish_readiness import check as readiness


URL = ("https://raw.githubusercontent.com/chenmu2024/ai-news-blog/main/"
       "content_os/assets/ai-scenes/parenting/2026-10-13/example.webp")
BYTES = b"verified-original-generated-image-bytes"
SHA = hashlib.sha256(BYTES).hexdigest()


def article(*, profile="parenting", day="2026-10-13", url=URL,
            sha=SHA, rights="ai_created_owned", genid="imagegen-verified-123"):
    import json
    rec = dict(profile=profile, article_date=day, image_url=url, sha256=sha,
               generator="openai_image_gen", generation_id=genid,
               rights=rights, synthetic=True, scene_role="illustration",
               scene_description="真实生成的一幅具有生活质感的写实家庭场景示意画面",
               pretends_to_be_real_person_or_record=False)
    return "# 家庭政策专题\n\n<!-- AI_SCENE " + json.dumps(rec, ensure_ascii=False) + " -->\n\n" + (
        "![写实生活场景](" + url + ")\n<!-- WECHAT_CARD {\"title\":\"流程\",\"items\":[]} -->")


class AiSceneRules(unittest.TestCase):
    def test_old_confirmed_not_rejected(self):
        self.assertEqual(check("parenting", "2026-10-12", "# 已确认旧草稿")[0], [])
        self.assertEqual(check("fashion", "2026-10-13", "# 明星真实照片")[0], [])

    def test_card_only_is_not_ai_scene(self):
        post = '# 测试\n<!-- WECHAT_CARD {"title":"信息卡","items":[]} -->'
        for key in ("qiezhi", "wechat", "business", "zizhitongjian", "parenting", "jingyun"):
            self.assertIn("ai_scene_missing", " ".join(check(key, "2026-10-13", post)[0]))

    def test_real_scene_manifest_and_actual_bytes(self):
        post = article()
        self.assertEqual(check("parenting", "2026-10-13", post)[0], [])
        self.assertEqual(verify_bytes("parenting", "2026-10-13", post,
                         getter=lambda _: BYTES), [])
        self.assertIn("asset SHA256 mismatch", " ".join(verify_bytes(
            "parenting", "2026-10-13", post, getter=lambda _: b"other bytes")))

    def test_private_ai_metadata_never_leaks_into_wechat_body(self):
        from content_os.image_resilience import strip_image_backup_notes
        post = article()
        public = strip_image_backup_notes(post)
        self.assertNotIn("AI_SCENE", public)
        self.assertNotIn("generation_id", public)
        self.assertIn("![写实生活场景]", public)
        self.assertIn("WECHAT_CARD", public)

    def test_false_provenance_is_rejected(self):
        post = article(rights="public_platform", genid="")
        self.assertTrue(check("parenting", "2026-10-13", post)[0])

    def test_external_stock_and_card_only_fail(self):
        post = article(url="https://images.pexels.com/picture.jpg")
        self.assertTrue(check("parenting", "2026-10-13", post)[0])
        self.assertIn("ai_scene", str(readiness("parenting", "# 家庭政策\n\n<!-- WECHAT_CARD {\"title\":\"卡\",\"items\":[]} -->", "2026-10-13")["errors"]))


if __name__ == "__main__":
    unittest.main()
