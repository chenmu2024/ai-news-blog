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
                title = f"一家{p} final" if p == "wechat" else f"{p} final"
                self._archive(root,p,day,title)
            folder=root/"content_os/title-decisions"; folder.mkdir(parents=True)
            data={"date":day,"profiles":{}}
            for p in PROFILES:
                prefix = "一家" if p == "wechat" else ""
                data["profiles"][p]={
                    "candidates":[f"{prefix}{p} A",f"{prefix}{p} B",f"{prefix}{p} final"],
                    "selected_title":f"{prefix}{p} final",
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


    def test_long_or_noncompliant_candidates_fail(self):
        from content_os.title_decisions import validate_record
        rec={"candidates":["一家短题","一家另外标题","这个标题超过三十二个字符需要在归档之前发现不合格而不是发布的时候再截断标题字数"],
             "selected_title":"一家短题",
             "rationale":"明确具体的事件、来源和账号适配度判断。",
             "basis":["official_source"],"verified_views":None}
        self.assertIn("candidate_title_exceeds_32_chars",validate_record("wechat",rec,"一家短题"))
        rec["candidates"]=["公司A","一家另外标题","一家短题"]
        self.assertIn("wechat_candidate_must_start_with_yijia",validate_record("wechat",rec,"一家短题"))
        rec["candidates"]=["一家短题","一家另外标题","一家第三个"]
        rec["verified_views"]=True
        self.assertIn("verified_views_must_be_nonnegative_integer_or_null",validate_record("wechat",rec,"一家短题"))

    def test_missing_file_stays_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            r=evaluate(Path(td),"2026-10-11")
            self.assertEqual(r["status"],"incomplete")
            self.assertEqual(r["complete_count"],0)

if __name__=="__main__":
    unittest.main()
