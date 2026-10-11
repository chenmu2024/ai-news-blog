"""Safe draft workflow dispatch: no duplicate run, journal or arbitrary archive."""
import tempfile
from pathlib import Path
import unittest
from content_os.safe_dispatch import classify, classify_verified_predraft_failure

class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.day="2026-10-11"
        self.path=self.root/"parenting/archive/2026-10-11.md"
        self.path.parent.mkdir(parents=True)
        self.path.write_text("# Title")
        self.msg="content(parenting): promote verified 2026-10-11 archive"
    def test_safe_first_dispatch(self):
        self.assertEqual(classify(self.root,"parenting",self.day,self.msg,[],{})[0],True)
    def test_old_or_manual_commit_not_dispatched(self):
        self.assertFalse(classify(self.root,"parenting",self.day,"manual copy",[],{})[0])
    def test_same_day_run_blocks(self):
        runs=[{"status":"completed","created_at":"2026-10-11T00:49:00Z"}]
        self.assertFalse(classify(self.root,"parenting",self.day,self.msg,runs,{})[0])
    def test_in_progress_run_blocks(self):
        runs=[{"status":"in_progress","created_at":"2026-10-10T23:59:00Z"}]
        self.assertFalse(classify(self.root,"parenting",self.day,self.msg,runs,{})[0])
    def test_journal_blocks(self):
        path=self.root/"parenting/status/draft-attempts/2026-10-11.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"state":"attempted"}')
        self.assertFalse(classify(self.root,"parenting",self.day,self.msg,[],{})[0])
    def test_receipt_blocks(self):
        self.assertFalse(classify(self.root,"parenting",self.day,self.msg,[],
                         {"article_path":"parenting/archive/2026-10-11.md"})[0])
    def test_exact_predraft_source_gate_failure_allows_one_safe_recovery(self):
        prior=[{"id":123,"status":"completed","conclusion":"failure",
                "event":"workflow_dispatch","created_at":"2026-10-11T01:03:07Z"}]
        jobs=[{"conclusion":"failure","steps":[
            {"name":"Draft idempotency preflight","conclusion":"success"},
            {"name":"Original-text source gate","conclusion":"failure"},
            {"name":"Create Zizhi Tongjian WeChat draft only","conclusion":"skipped"},
        ]}]
        path=self.root/"zizhitongjian/archive/2026-10-11.md"
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("# valid original",encoding="utf-8")
        msg="content(zizhitongjian): promote verified 2026-10-11 archive"
        self.assertEqual(classify_verified_predraft_failure(
            self.root,"zizhitongjian",self.day,msg,prior,{},jobs)[0],True)
        # No second attempt: once there are two same-day runs, STOP.
        self.assertEqual(classify_verified_predraft_failure(
            self.root,"zizhitongjian",self.day,msg,prior*2,{},jobs)[0],False)
        jobs[0]["steps"][2]["conclusion"]="success"
        self.assertEqual(classify_verified_predraft_failure(
            self.root,"zizhitongjian",self.day,msg,prior,{},jobs)[0],False)

    def test_other_accounts_cannot_recover_failed_ones_automatically(self):
        self.assertFalse(classify_verified_predraft_failure(
            self.root,"parenting",self.day,self.msg,[],{},[])[0])

    def test_unverified_history_blocks(self):
        self.assertFalse(classify(self.root,"parenting",self.day,self.msg,[{}]*100,{})[0])

if __name__=="__main__":
    unittest.main()
