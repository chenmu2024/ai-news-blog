import json
import tempfile
import unittest
from pathlib import Path
from content_os.humanizer.pollution_gate import check

class PollutionGateTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.day="2026-10-14"
        self.path=self.root/"content_os/editorial-reviews/wechat"/(self.day+".json")
        self.path.parent.mkdir(parents=True)
    def write(self,pollution):
        rec={"humanizer":{"reference_examples":[
            {"origin":"project_bank","reference_id":"seg-a"},
            {"origin":"project_bank","reference_id":"seg-b"},
            {"origin":"web_benchmark","reference_id":"web-c"}],
            "pollution_check":pollution}}
        self.path.write_text(json.dumps(rec,ensure_ascii=False),"utf-8")
    def good(self):
        return {"engine":"private_exact_overlap_v1","status":"PASS","threshold_chars":24,
                "max_exact_overlap_chars":7,"reference_ids_checked":["seg-a","seg-b"],
                "web_references_checked":True}
    def test_passes_complete_private_scan(self):
        self.write(self.good())
        self.assertEqual(check(self.root,"wechat",self.day)["status"],"PASS")
    def test_blocks_overlap(self):
        x=self.good();x["max_exact_overlap_chars"]=31;x["status"]="FAIL";self.write(x)
        self.assertEqual(check(self.root,"wechat",self.day)["status"],"FAIL")
    def test_blocks_missing_project_reference(self):
        x=self.good();x["reference_ids_checked"]=["seg-a"];self.write(x)
        self.assertIn("humanizer_pollution_did_not_check_all_project_references",
                      check(self.root,"wechat",self.day)["errors"])
    def test_old_day_not_retroactive(self):
        self.assertEqual(check(self.root,"wechat","2026-10-13")["status"],"NOT_REQUIRED")
if __name__=="__main__":
    unittest.main()
