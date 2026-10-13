"""Offline source provenance regression: rate-limit resilience without weakening quotes."""
import unittest
from unittest.mock import patch
from zizhitongjian import source_gate as gate

class ExactVolumeReuse(unittest.TestCase):
    def test_rendered_primary_proves_all_quotes_with_one_request(self):
        body = "徙木立信，法之不行，自上犯之。夫信者，人君之大宝也。"
        with (patch.object(gate, "fetch_page", return_value=body) as rendered,
              patch.object(gate, "fetch_wikisource_text") as api,
              patch.object(gate, "fetch_wikisource_wikitext") as raw):
            url = "https://zh.wikisource.org/zh-hant/資治通鑑/卷002"
            self.assertTrue(gate.source_contains(url, "法之不行，自上犯之"))
            self.assertTrue(gate.source_contains(url, "夫信者，人君之大宝也"))
            self.assertEqual(rendered.call_count, 2)
            api.assert_not_called()
            raw.assert_not_called()

    def test_429_fallback_uses_exact_volume_secondary_representation(self):
        import requests
        url = "https://zh.wikisource.org/zh-hant/資治通鑑/卷002"
        with (patch.object(gate, "fetch_page", side_effect=requests.HTTPError("429")),
              patch.object(gate, "fetch_wikisource_text", return_value="夫信者人君之大宝也") as api,
              patch.object(gate, "fetch_wikisource_wikitext") as raw):
            self.assertTrue(gate.source_contains(url, "夫信者，人君之大宝也"))
            api.assert_called_once_with(url, "zh-hant")
            raw.assert_not_called()

    def test_source_mismatch_fails_closed(self):
        url = "https://zh.wikisource.org/zh-hant/資治通鑑/卷002"
        with (patch.object(gate, "fetch_page", return_value="不同卷的内容"),
              patch.object(gate, "fetch_wikisource_text", return_value="不同卷的内容"),
              patch.object(gate, "fetch_wikisource_wikitext", return_value="不同卷的内容")):
            self.assertFalse(gate.source_contains(url, "伪造原典引文"))

    def test_entire_source_outage_fails_closed(self):
        url = "https://zh.wikisource.org/zh-hant/資治通鑑/卷002"
        with (patch.object(gate, "fetch_page", side_effect=RuntimeError("429")),
              patch.object(gate, "fetch_wikisource_text", side_effect=RuntimeError("429")),
              patch.object(gate, "fetch_wikisource_wikitext", side_effect=RuntimeError("429"))):
            with self.assertRaisesRegex(RuntimeError, "全部原文表示不可访问"):
                gate.source_contains(url, "原文")

if __name__ == "__main__":
    unittest.main()
