import json
import tempfile
import unittest
from pathlib import Path
from content_os.reading_feedback import load_jsonl, summarize, headline_features

class ReadingFeedbackTests(unittest.TestCase):
    def test_missing_views_are_not_inferred(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"manual.jsonl"
            p.write_text(json.dumps({"profile":"business","date":"2026-10-10","title":"泡泡玛特之后，真正难的是增长","views":None,"source":"manual observation"},ensure_ascii=False)+"\n","utf-8")
            rows=load_jsonl(p)
            result=summarize(rows)["business"]
            self.assertEqual(result["records"],1)
            self.assertEqual(result["numeric_records"],0)
            self.assertIsNone(result["avg_views"])

    def test_numeric_feedback_uses_only_real_integer_views(self):
        rows=[
            {"profile":"business","date":"2026-10-01","title":"瑞幸之后，真正难的是复制","views":100,"source":"manual"},
            {"profile":"business","date":"2026-10-02","title":"泡泡玛特之后，真正难的是增长","views":200,"source":"manual"},
        ]
        result=summarize(rows)["business"]
        self.assertEqual(result["numeric_records"],2)
        self.assertEqual(result["avg_views"],150)

    def test_headline_features_are_explainable(self):
        f=headline_features("一家AI公司融资5亿之后，真正难的是什么？")
        self.assertIn("question",f)
        self.assertIn("contrast",f)
        self.assertIn("number",f)
        self.assertIn("starts_with_一家",f)

if __name__=="__main__":
    unittest.main()
