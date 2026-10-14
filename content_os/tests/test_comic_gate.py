"""Regression: A-F require comic packages; fashion and historical days retain old behavior."""
import copy
import hashlib
import json
import unittest
from content_os.comic_gate import check, body_without_marker, binding_sha256, required

BASE = "https://raw.githubusercontent.com/chenmu2024/ai-news-blog/main/content_os/assets/ai-scenes/"
DAY = "2026-10-14"

def story(profile="parenting"):
    images = []
    panels = []
    labels = ("hook","misconception","conflict","evidence","choice",
              "action","reveal","action","resolution","ending")
    for i in range(5):
        url = BASE + f"{profile}/{DAY}/strip-{i}.png"
        sha = hashlib.sha256(f"binary-{i}".encode()).hexdigest()
        images.append({"url": url, "sha256": sha})
    for j, beat in enumerate(labels):
        panels.append({"id":f"p{j+1}", "shot":"medium" if j % 2 else "close",
                       "visible_action":f"主角翻看不同的材料第{j+1}页",
                       "setting":f"房间镜头{j+1}","beat":beat,"strip_index":j//2})
    pkg = {"mode":"original_sequential_comic","profile":profile,"article_date":DAY,
           "panels":panels, "images":images,
           "editorial":{k:True for k in ("actual_images_seen","mobile_preview_seen","fact_review","humanizer_v4","originality_review")},
           "approval":{"status":"approved","by":"user","source":"chat","message_text":"同步草稿",
                       "approved_at":"2026-10-14T11:00:00+08:00","body_sha256":""}}
    text = "# 一家AI公司获得订单后的难题\n" if profile == "wechat" else "# 办理待遇前的两次确认\n"
    text += "这是一个原创虚构情境演绎。\n\n"
    for item in images:
        text += f"![漫画](\u0024URL)\n".replace("$URL",item["url"])
        text += "<!-- AI_SCENE " + json.dumps({"image_url":item["url"],"sha256":item["sha256"],"synthetic":True},ensure_ascii=False) + " -->\n"
    def wrap(x): return text + "<!-- COMIC_PACKAGE " + json.dumps(x,ensure_ascii=False) + " -->\n"
    pkg["approval"]["body_sha256"] = binding_sha256(wrap(pkg))
    return wrap(pkg)

class ComicPolicyTests(unittest.TestCase):
    def test_old_dates_and_fashion_unaffected(self):
        self.assertFalse(required("parenting","2026-10-13"))
        self.assertFalse(required("fashion",DAY))
        self.assertEqual(check("fashion",DAY,"# 真实明星照片"),[])
    def test_6_profiles_valid_metadata(self):
        for p in ("qiezhi","wechat","business","zizhitongjian","parenting","jingyun"):
            with self.subTest(p=p):
                self.assertEqual(check(p,DAY,story(p)),[])
    def test_no_manifest_blocks(self):
        self.assertIn("comic_package_requires_exactly_one_manifest",check("parenting",DAY,"# 纯文字"))
    def test_hash_binding_blocks_edits(self):
        v=story().replace("办理待遇前的两次确认","办理待遇前的第三次确认")
        self.assertIn("comic_user_approved_body_hash_mismatch",check("parenting",DAY,v))
    def test_missing_approval_blocks(self):
        s=story()
        self.assertIn("comic_user_approval_not_recorded_for_exact_candidate",
                      check("parenting",DAY,s.replace('"status": "approved"','"status": "pending"')))
    def test_duplicate_panels_block(self):
        s=story()
        self.assertIn("comic_panel_2_missing_visual_action_shot_or_setting",
                      check("parenting",DAY,s.replace("主角翻看不同的材料第2页","a")))

if __name__ == "__main__": unittest.main()
