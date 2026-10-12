"""Offline regression for the seven-publisher contracts and gate provenance."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_readiness as readiness
import gate_trace


def card(role):
    if role == "inline":
        return '<!-- QIEZHI_CARD {"role":"inline","title":"方法卡","items":[{"name":"一步"}]} -->'
    return '<!-- QIEZHI_CARD {"role":"cover","title":"封面卡"} -->'


class ReadyTests(unittest.TestCase):
    def test_qiezhi_stock_photos_without_card_are_rejected(self):
        md = "# 本日文章\n\n![Photo](https://www.example.com/1.jpg)\n![Photo](https://www.example.com/2.jpg)"
        r = readiness.check("qiezhi", md)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("QIEZHI_CARD", " ".join(r["errors"]))

    def test_qiezhi_repaired_cover_and_inline_are_accepted(self):
        result = readiness.check("qiezhi", "# 本日文章\n" + card("cover") + "\n" + card("inline"), "2026-10-12")
        self.assertEqual(result["status"], "PASS")

    def test_malformed_json_is_rejected_before_wechat(self):
        result = readiness.check("qiezhi", "# X\n" + card("cover") + "\n<!-- QIEZHI_CARD {bad} -->")
        self.assertEqual(result["status"], "FAIL")

    def test_future_long_wechat_title_fails_before_draft_add(self):
        headline = "一家技术公司换了新老板以后还要重新寻找自己的长期增长方向和市场竞争位置以及新产品路线"
        doc = "# " + headline + "\n<!-- WECHAT_CARD {\"title\":\"分析\",\"items\":[]} -->"
        self.assertGreater(len(headline), 32)
        self.assertEqual(readiness.check("wechat", doc, "2026-10-11")["status"], "FAIL")
        self.assertEqual(readiness.check("wechat", doc, "2026-10-10")["status"], "PASS")

    def test_temp_candidate_cannot_bypass_current_title_limit(self):
        headline = "一家人工智能公司为了寻找增长而不断增加客户以及开发很多不同业务方向仍然没有找到确定的盈利路径"
        self.assertGreater(len(headline), 32)
        doc = "# " + headline + "\n<!-- WECHAT_CARD {\"title\":\"案例\",\"items\":[]} -->"
        self.assertEqual(readiness.check("wechat", doc)["status"], "FAIL")

    def test_ai_title_starts_with_a_company(self):
        self.assertEqual(readiness.check("wechat", "# 一家AI公司如何赚钱\n<!-- WECHAT_CARD {\"title\":\"案例\",\"items\":[]} -->", "2026-10-12")["status"], "PASS")
        self.assertEqual(readiness.check("wechat", "# AI巨头赚钱了\n<!-- WECHAT_CARD {\"title\":\"案例\",\"items\":[]} -->", "2026-10-12")["status"], "FAIL")

    def test_fashion_requires_manifest_and_five_unique_photos(self):
        images = [{"image_url": f"https://images.example.com/{i}.jpg"} for i in range(5)]
        lines = [f"![Look {i}](https://images.example.com/{i}.jpg)" for i in range(5)]
        md = "<!-- FASHION_SOURCE\n" + json.dumps({"images": images}) + "\n-->\n# 日系搭配\n" + "\n".join(lines)
        self.assertEqual(readiness.check("fashion", md)["status"], "PASS")
        self.assertEqual(readiness.check("fashion", md.replace(lines[4], ""))["status"], "FAIL")

    def test_zztj_requires_original_text_manifest(self):
        self.assertEqual(readiness.check("zizhitongjian", "# 智伯故事\n<!-- WECHAT_CARD {\"title\":\"人物\",\"items\":[]} -->")["status"], "FAIL")

    def test_gate_binding_rejects_stale_fail_and_records_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            article = Path("parenting/archive/2026-10-11.md")
            (root / article).parent.mkdir(parents=True)
            (root / article).write_text("# 本日正文", encoding="utf-8")
            gate_dir = root / "parenting/status"
            gate_dir.mkdir(parents=True)
            for name in gate_trace.GATES:
                (gate_dir / name).write_text('{"status":"PASS"}', encoding="utf-8")
            old = Path.cwd()
            try:
                import os
                os.chdir(root)
                self.assertEqual(gate_trace.bind(article, "parenting", root), list(gate_trace.GATES))
                for name in gate_trace.GATES:
                    data = json.loads((gate_dir / name).read_text("utf-8"))
                    self.assertEqual(data["article_sha256"], hashlib.sha256((root/article).read_bytes()).hexdigest())
                    self.assertEqual(data["article_path"], article.as_posix())
                (gate_dir / "visual-gate.json").write_text('{"status":"FAIL"}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "non-PASS"):
                    gate_trace.bind(article, "parenting", root)
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
