"""Offline checks for safe in-place celebrity revision, no WeChat credentials."""
import ast
import json
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "fashion" / "update_existing_draft.py"


class TestFashionRevision(unittest.TestCase):
    def test_existing_media_id_update_only_never_add(self):
        content = SCRIPT.read_text("utf-8")
        self.assertIn('"/draft/update"', content)
        self.assertIn('"/draft/get"', content)
        self.assertNotIn('"/draft/add"', content)
        self.assertIn("_media_id_from_verified_run(existing)", content)
        self.assertIn("draft_media_id", content)
        self.assertIn("_identical_revision", content)

    def test_wire_json_decodes_chinese_even_if_response_charset_is_wrong(self):
        tree = ast.parse(SCRIPT.read_text("utf-8"))
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_wechat_json")
        namespace = {"json": json}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SCRIPT), "exec"), namespace)
        sample = {"news_item": [{"title": "日本女生秋天把西装穿得松弛，关键不是买大一码"}]}
        wire = json.dumps(sample, ensure_ascii=False).encode("utf-8")
        fake = types.SimpleNamespace(content=wire)
        self.assertEqual(namespace["_wechat_json"](fake), sample)

    def test_original_archive_immutable_in_updater(self):
        source = SCRIPT.read_text("utf-8")
        self.assertNotIn("ORIGINAL.write_", source)
        self.assertNotIn("RECEIPT.write_", source)
        self.assertIn("fashion/revisions", source)


if __name__ == "__main__":
    unittest.main()
