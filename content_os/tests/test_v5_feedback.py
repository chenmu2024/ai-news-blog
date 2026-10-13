import json
import tempfile
import unittest
from pathlib import Path

from content_os.article_feedback_database import build as build_db
from content_os.title_performance_analyzer import analyze
from content_os.account_learning_profile import build as build_profiles

class V5FeedbackTests(unittest.TestCase):
    def _archive(self,root,profile,day,title):
        p=root/profile/"archive"/f"{day}.md";p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(f"# {title}\n\n正文\n","utf-8")

    def test_missing_metrics_stay_null(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self._archive(root,"business","2026-10-01","政策标题")
            db=build_db(root)
            r=db["records"][0]
            self.assertIsNone(r["metrics"]["views"])
            self.assertEqual(r["performance_level"],"insufficient_data")

    def test_manual_metrics_are_joined_without_inference(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self._archive(root,"business","2026-10-01","政策标题")
            p=root/"content_os/reading-feedback/manual.jsonl";p.parent.mkdir(parents=True)
            p.write_text(json.dumps({"profile":"business","date":"2026-10-01","title":"政策标题",
                "views":123,"shares":4,"source":"verified"},ensure_ascii=False)+"\n","utf-8")
            db=build_db(root,p)
            self.assertEqual(db["records"][0]["metrics"]["views"],123)
            self.assertEqual(db["records"][0]["metrics"]["shares"],4)
            self.assertIsNone(db["records"][0]["metrics"]["likes"])

    def test_title_analysis_refuses_small_sample(self):
        db={"records":[{"profile":"business","headline_features":["number"],"metrics":{"views":100}}]}
        r=analyze(db)["profiles"]["business"]
        self.assertEqual(r["status"],"insufficient_data")
        self.assertEqual(r["observations"],[])

    def test_learning_profile_does_not_auto_apply(self):
        db={"records":[]};titles={"profiles":{}}
        r=build_profiles(db,titles)["profiles"]["jingyun"]
        self.assertFalse(r["auto_apply"])
        self.assertEqual(r["evidence_level"],"insufficient")
        self.assertEqual(r["next_experiment"]["type"],"collect_feedback")

    def test_five_verified_records_can_enter_early_learning(self):
        rows=[]
        for i in range(5):
            rows.append({"profile":"wechat","humanizer_roles":["opening","detail"],
                         "headline_features":["contrast"],"metrics":{"views":100+i*10}})
        db={"records":rows}
        titles=analyze(db)
        r=build_profiles(db,titles)["profiles"]["wechat"]
        self.assertEqual(r["evidence_level"],"early")
        self.assertFalse(r["auto_apply"])

if __name__=="__main__":
    unittest.main()
