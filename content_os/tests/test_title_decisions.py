import json
import tempfile
import unittest
from pathlib import Path
from content_os.title_decisions import evaluate

PROFILES=("qiezhi","wechat","business","zizhitongjian","parenting","jingyun","fashion")

class TitleDecisionTests(unittest.TestCase):
    def _archive(self,root,profile,day,title):
        p=Path(root)/profile/"archive"/f"{day}.md"
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(f"# {title}\n\nbody\n","utf-8")

    def test_requires_three_unique_candidates_and_archive_match(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); day="2026-10-11"
            for p in PROFILES:
                self._archive(root,p,day,f"{p} final")
            folder=root/"content_os/title-decisions"; folder.mkdir(parents=True)
            data={"date":day,"profiles":{}}
            for p in PROFILES:
                data["profiles"][p]={
                    "candidates":[f"{p} A",f"{p} B",f"{p} final"],
                    "selected_title":f"{p} final",
                    "rationale":"具体账号匹配、事实清楚且与近30天标题不重复。",
                    "basis":["account_fit","specificity","30d_novelty"],
                    "verified_views":None
                }
            (folder/f"{day}.json").write_text(json.dumps(data,ensure_ascii=False),"utf-8")
            r=evaluate(root,day)
            self.assertEqual(r["status"],"complete")
            self.assertEqual(r["complete_count"],7)

    def test_duplicate_candidates_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); day="2026-10-11"
            self._archive(root,"business",day,"Final")
            folder=root/"content_os/title-decisions"; folder.mkdir(parents=True)
            (folder/f"{day}.json").write_text(json.dumps({"profiles":{"business":{
                "candidates":["A","A","Final"],"selected_title":"Final",
                "rationale":"这个选择理由长度已经足够用于验证测试。",
                "basis":["account_fit"],"verified_views":None
            }}}),"utf-8")
            r=evaluate(root,day)
            self.assertIn("candidate_titles_must_be_unique",r["profiles"]["business"]["errors"])

    def test_missing_file_stays_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            r=evaluate(Path(td),"2026-10-11")
            self.assertEqual(r["status"],"incomplete")
            self.assertEqual(r["complete_count"],0)

if __name__=="__main__":
    unittest.main()
