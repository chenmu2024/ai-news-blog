import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from content_os.daily_healthcheck import audit_profile

class DraftHealthSemanticsTests(unittest.TestCase):
    def _base(self, root: Path, day: str, status_media_id=None):
        profile="qiezhi"
        article=f"# 测试标题\n\n正文\n".encode("utf-8")
        archive=root/profile/"archive"/f"{day}.md"
        today=root/profile/"articles"/"today.md"
        status_dir=root/profile/"status"
        archive.parent.mkdir(parents=True)
        today.parent.mkdir(parents=True)
        status_dir.mkdir(parents=True)
        archive.write_bytes(article)
        today.write_bytes(article)
        sha=hashlib.sha256(article).hexdigest()
        status={"status":"success","title":"测试标题","article_path":f"{profile}/archive/{day}.md","article_sha256":sha}
        if status_media_id:
            status["draft_media_id"]=status_media_id
        (status_dir/"latest.json").write_text(json.dumps(status,ensure_ascii=False),"utf-8")
        for gate in ("quality-gate.json","visual-gate.json"):
            g={"status":"PASS"}
            if day >= "2026-10-11":
                g.update({"article_sha256":sha,"article_path":f"{profile}/archive/{day}.md"})
            (status_dir/gate).write_text(json.dumps(g),"utf-8")
        return profile,archive,sha,status_dir

    def test_legacy_repo_success_is_not_durable_confirmation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            profile,_,_,_=self._base(root,"2026-10-10")
            r=audit_profile(root,profile,"2026-10-10")
            self.assertEqual(r["status"],"success")
            self.assertEqual(r["draft_confirmation_mode"],"legacy_repo_receipt_only")
            self.assertFalse(r["draft_confirmed"])

    def test_legacy_media_id_is_distinguished_from_journal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            profile,_,_,_=self._base(root,"2026-10-10","legacy-id")
            r=audit_profile(root,profile,"2026-10-10")
            self.assertEqual(r["draft_confirmation_mode"],"legacy_status_media_id")
            self.assertFalse(r["draft_confirmed"])

    def test_new_day_requires_confirmed_wechat_image_readback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            profile, article, checksum, status_dir = self._base(root, "2026-10-13", "mid")
            journal = status_dir / "draft-attempts" / "2026-10-13.json"
            journal.parent.mkdir()
            journal.write_text(json.dumps({
                "state": "confirmed", "draft_media_id": "mid",
                "article_path": article.relative_to(root).as_posix(),
                "article_sha256": checksum,
            }), "utf-8")
            missing = audit_profile(root, profile, "2026-10-13")
            self.assertIn("wechat_inline_image_readback_missing_or_mismatched",
                          missing["errors"])
            receipt = status_dir / "draft-readback" / "2026-10-13.json"
            receipt.parent.mkdir()
            receipt.write_text(json.dumps({
                "draft_get_verified": True, "draft_media_id": "mid",
                "article_path": article.relative_to(root).as_posix(),
                "article_sha256": checksum, "article_date": "2026-10-13",
                "inline_image_count": 2,
            }), "utf-8")
            confirmed = audit_profile(root, profile, "2026-10-13")
            self.assertTrue(confirmed["wechat_inline_readback_verified"])
            self.assertEqual(confirmed["status"], "success")

    def test_2026_10_13_accepts_gate_bound_readback_without_new_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            profile, article, checksum, status_dir = self._base(root, "2026-10-13", "mid")
            journal = status_dir / "draft-attempts" / "2026-10-13.json"
            journal.parent.mkdir()
            journal.write_text(json.dumps({
                "state": "confirmed", "draft_media_id": "mid",
                "article_path": article.relative_to(root).as_posix(),
                "article_sha256": checksum,
            }), "utf-8")
            visual = status_dir / "visual-gate.json"
            gate = json.loads(visual.read_text("utf-8"))
            gate["wechat_inline_readback"] = {
                "draft_get_verified": True, "draft_media_id": "mid",
                "article_path": article.relative_to(root).as_posix(),
                "article_sha256": checksum, "article_date": "2026-10-13",
                "inline_image_count": 1,
            }
            visual.write_text(json.dumps(gate), "utf-8")
            result = audit_profile(root, profile, "2026-10-13")
            self.assertTrue(result["wechat_inline_readback_verified"])
            self.assertEqual(result["status"], "success")

    def test_rollout_requires_matching_confirmed_journal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            profile,archive,sha,status_dir=self._base(root,"2026-10-11")
            journal=status_dir/"draft-attempts"/"2026-10-11.json"
            journal.parent.mkdir()
            journal.write_text(json.dumps({
                "state":"confirmed","profile":profile,
                "article_path":archive.relative_to(root).as_posix(),
                "article_sha256":sha,"title":"测试标题",
                "run_id":"1","draft_media_id":"media-1"
            },ensure_ascii=False),"utf-8")
            r=audit_profile(root,profile,"2026-10-11")
            self.assertEqual(r["status"],"success")
            self.assertEqual(r["draft_confirmation_mode"],"confirmed_journal")
            self.assertTrue(r["draft_confirmed"])

if __name__=="__main__":
    unittest.main()
