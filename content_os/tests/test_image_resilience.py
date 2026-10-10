"""Offline reliability regressions; no WeChat calls or network requests."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import image_resilience as m
from PIL import Image


def image_bytes(mode="RGB", fmt="JPEG", color=(80, 90, 100)):
    img = Image.new(mode, (400, 350), color)
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


class Response:
    def __init__(self, url, status=200, data=None, content_type="image/jpeg"):
        self.url = url
        self.status_code = status
        self.content = data if data is not None else image_bytes()
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError("HTTP " + str(self.status_code))


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses[url]


class ImageResilienceTests(unittest.TestCase):
    def test_simple_jpeg_preflight_and_preserves_original_address(self):
        url = "https://images.example.com/one.jpg"
        session = FakeSession({url: Response(url)})
        out = m.prepare_images("# Test\n![Image](" + url + ")", "business", session=session)
        self.assertEqual(set(out), {url})
        self.assertEqual(out[url][1:], ("image/jpeg", ".jpg"))
        self.assertTrue(out[url][0].startswith(bytes.fromhex("ffd8")))

    def test_pexels_avif_is_retried_as_explicit_jpeg(self):
        primary = "https://images.pexels.com/photos/123/pexels-photo-123.jpeg?auto=compress&cs=tinysrgb&w=1200"
        alt = m.pexels_jpeg_variant(primary)
        self.assertIn("fm=jpg", alt)
        self.assertNotIn("auto=", alt)
        session = FakeSession({
            primary: Response(primary, data=b"not-decodable-avif", content_type="image/avif"),
            alt: Response(alt, data=image_bytes()),
        })
        with patch.object(m.time, "sleep", return_value=None):
            out = m.prepare_images("![Pexels](" + primary + ")", "parenting", session=session)
        self.assertIn(primary, out)
        self.assertEqual([p[0] for p in session.calls], [primary, alt])

    def test_403_uses_only_verifiable_editorial_backup(self):
        first = "https://images.example.com/one.jpg"
        backup = "https://images.pexels.com/photos/222/pexels-photo-222.jpeg?fm=jpg"
        descriptor = {"images": [{"primary": first, "alternatives": [{
            "url": backup, "source_page_url": "https://www.pexels.com/photo/222/",
            "rights": "pexels_license", "verified": True, "subject_match": True
        }]}]}
        article = ("<!-- IMAGE_BACKUPS\n" + json.dumps(descriptor) +
                   "\n-->\n# Test\n![Actual subject](" + first + ")")
        session = FakeSession({
            first: Response(first, status=403),
            backup: Response(backup, data=image_bytes()),
        })
        out = m.prepare_images(article, "business", session=session)
        self.assertIn(first, out)
        self.assertEqual(len(session.calls), 2)
        self.assertNotIn("IMAGE_BACKUPS", m.strip_image_backup_notes(article))

    def test_403_does_not_switch_to_unlicensed_or_unrelated_image(self):
        first = "https://images.example.com/one.jpg"
        unlicensed = "https://example.net/unrelated.jpg"
        descriptor = {"images": [{"primary": first, "alternatives": [{
            "url": unlicensed, "source_page_url": "https://example.net/article",
            "rights": "public_platform", "verified": True, "subject_match": False
        }]}]}
        article = "<!-- IMAGE_BACKUPS\n" + json.dumps(descriptor) + "\n-->\n![Actual](" + first + ")"
        session = FakeSession({first: Response(first, status=403)})
        with self.assertRaisesRegex(ValueError, "five distinct"):
            m.prepare_images(article, "fashion", session=session)
        self.assertEqual(len(session.calls), 0)  # Fashion must first have 5 distinct images
        # With no fashion minimum, the unlicensed alternate remains unreachable.
        with self.assertRaisesRegex(RuntimeError, "Preflight failed"):
            m.prepare_images(article, "business", session=session)
        self.assertEqual([x[0] for x in session.calls], [first])

    def test_licensed_scene_photo_fallback_allowed_for_four_profiles(self):
        first = "https://images.example.com/old-study-photo.jpg"
        replacement = "https://images.pexels.com/photos/999/pexels-photo-999.jpeg?fm=jpg"
        metadata = {"images": [{"primary": first, "alternatives": [{
            "image_url": replacement,
            "source_page_url": "https://www.pexels.com/photo/999/",
            "rights": "pexels_license", "verified": True,
            "scene_match": True, "subject_match": False,
        }]}]}
        article = ("<!-- IMAGE_BACKUPS\n" + json.dumps(metadata) +
                   "\n-->\n![Reading at a desk](" + first + ")")
        for profile in ("qiezhi", "zizhitongjian", "parenting", "jingyun"):
            with self.subTest(profile=profile):
                session = FakeSession({
                    first: Response(first, status=403),
                    replacement: Response(replacement, data=image_bytes()),
                })
                prepared = m.prepare_images(article, profile, session=session)
                self.assertIn(first, prepared)
                self.assertEqual([u for u, _ in session.calls],
                                 [first, replacement])
                self.assertEqual(prepared[first][1], "image/jpeg")

    def test_scene_only_fallback_does_not_weaken_three_restricted_profiles(self):
        first = "https://images.example.com/pictured-real-shop.jpg"
        unrelated = "https://images.pexels.com/photos/999/pexels-photo-999.jpeg?fm=jpg"
        metadata = {"images": [{"primary": first, "alternatives": [{
            "image_url": unrelated,
            "source_page_url": "https://www.pexels.com/photo/999/",
            "rights": "pexels_license", "verified": True,
            "scene_match": True, "subject_match": False,
        }]}]}
        five = "\n".join("![look](https://images.example.com/look" + str(i) +
                           ".jpg)" for i in range(4))
        base = ("<!-- IMAGE_BACKUPS\n" + json.dumps(metadata) +
                "\n-->\n![real product](" + first + ")")
        for profile in ("wechat", "business", "fashion"):
            with self.subTest(profile=profile):
                session = FakeSession({first: Response(first, status=403)})
                with self.assertRaisesRegex(RuntimeError, "Preflight failed"):
                    m.prepare_images(base + ("\n" + five if profile == "fashion" else ""),
                                     profile, session=session)
                self.assertEqual([u for u, _ in session.calls], [first])

    def test_scene_fallback_requires_license_and_verified_source(self):
        first = "https://images.example.com/one.jpg"
        backup = "https://images.pexels.com/photos/222/pexels-photo-222.jpeg"
        for bad in (
            {"rights": "public_platform", "verified": True, "scene_match": True},
            {"rights": "pexels_license", "verified": False, "scene_match": True},
            {"rights": "pexels_license", "verified": True, "scene_match": False},
        ):
            with self.subTest(bad=bad):
                descriptor = {"images": [{"primary": first, "alternatives": [{
                    "image_url": backup,
                    "source_page_url": "https://www.pexels.com/photo/222/",
                    **bad,
                }]}]}
                article = ("<!-- IMAGE_BACKUPS\n" + json.dumps(descriptor) +
                           "\n-->\n![illustration](" + first + ")")
                session = FakeSession({first: Response(first, status=403)})
                with self.assertRaisesRegex(RuntimeError, "Preflight failed"):
                    m.prepare_images(article, "parenting", session=session)
                self.assertEqual(len(session.calls), 1)

    def test_transparent_png_becomes_jpeg_with_white_background(self):
        url = "https://images.example.com/clear.png"
        png = image_bytes(mode="RGBA", fmt="PNG", color=(255, 0, 0, 120))
        session = FakeSession({url: Response(url, data=png, content_type="image/png")})
        out = m.prepare_images("![Transparent](" + url + ")", "jingyun", session=session)
        decoded = Image.open(io.BytesIO(out[url][0]))
        self.assertEqual(decoded.format, "JPEG")
        self.assertEqual(decoded.mode, "RGB")

    def test_html_or_failed_server_never_counts_as_image(self):
        url = "https://img.example.com/bad.jpg"
        session = FakeSession({url: Response(url, data=b"<html>denied</html>", content_type="text/html")})
        with self.assertRaisesRegex(RuntimeError, "Preflight failed"):
            m.prepare_images("![Forbidden](" + url + ")", "wechat", session=session)

    def test_qiezhi_uploaded_stock_url_does_not_replace_internal_card_url(self):
        # Import publisher without calling the real WeChat API.
        script = Path(__file__).resolve().parents[2] / "qiezhi" / "publish_draft.py"
        with patch.dict(os.environ, {"WECHAT_APP_ID": "test",
                                     "WECHAT_APP_SECRET": "test"}):
            spec = importlib.util.spec_from_file_location("test_qiezhi_publisher", script)
            pub = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pub)
        photo = "https://images.pexels.com/photos/333/pexels-photo-333.jpeg?fm=jpg"
        card = "https://mmbiz.qpic.cn/sz_mmbiz_png/test-image/640"
        markdown_text = ("![licensed lifestyle scene](" + photo + ")" +
                         "\\n![rendered knowledge card](" + card + ")")
        staged = {photo: (image_bytes(), "image/jpeg", ".jpg")}
        with patch.object(pub, "upload_body",
                          return_value="https://mmbiz.qpic.cn/approved-stock.jpg") as upload:
            out = pub.replace_stock_images(markdown_text, "fake-token", staged)
        upload.assert_called_once()
        self.assertIn("https://mmbiz.qpic.cn/approved-stock.jpg", out)
        self.assertIn(card, out)
        self.assertNotIn(photo, out)

    def test_only_public_https_hosts(self):
        for url in ["http://example.com/a.jpg", "https://localhost/a.jpg",
                    "https://127.0.0.1/a.jpg", "https://10.0.0.1/a.jpg"]:
            self.assertFalse(m.public_https(url))
        self.assertTrue(m.public_https("https://images.pexels.com/p.jpg"))

    def test_external_html_img_cannot_bypass_early_media_staging(self):
        html = '<img src="https://example.com/unaudited-photo.jpg" alt="photo">'
        with self.assertRaisesRegex(ValueError, "must be Markdown"):
            m.prepare_images(html, "business")

    def test_staged_jpeg_is_reused_without_network(self):
        url = "https://images.example.com/coffee.jpg"
        markdown = "# Brand story\\n![Real photo](" + url + ")"
        source = FakeSession({url: Response(url)})
        with tempfile.TemporaryDirectory() as temp:
            original = m.prepare_images(markdown, "business", session=source)
            self.assertEqual(len(source.calls), 1)
            m.save_prepared_cache(markdown, "business", original, Path(temp))
            blocked = FakeSession({})
            env = {"CONTENT_OS_IMAGE_CACHE_READ": "1", "CONTENT_OS_IMAGE_CACHE_DIR": temp}
            with patch.dict(os.environ, env):
                loaded = m.prepare_images(markdown, "business", session=blocked)
            self.assertEqual(loaded, original)
            self.assertEqual(blocked.calls, [])

    def test_cache_rejects_article_change_and_wrong_profile(self):
        url = "https://images.example.com/store.jpg"
        markdown = "# Store\\n![Store](" + url + ")"
        with tempfile.TemporaryDirectory() as temp:
            m.save_prepared_cache(markdown, "business",
                                  {url: (image_bytes(), "image/jpeg", ".jpg")}, Path(temp))
            env = {"CONTENT_OS_IMAGE_CACHE_READ": "1", "CONTENT_OS_IMAGE_CACHE_DIR": temp}
            with patch.dict(os.environ, env):
                with self.assertRaisesRegex(RuntimeError, "cache unavailable or tampered"):
                    m.prepare_images(markdown + "\\nChanged", "business")
                with self.assertRaisesRegex(RuntimeError, "cache unavailable or tampered"):
                    m.prepare_images(markdown, "parenting")

    def test_cache_rejects_corrupt_bytes_and_missing_manifest(self):
        url = "https://images.example.com/shop.jpg"
        markdown = "# Store\\n![Shop](" + url + ")"
        with tempfile.TemporaryDirectory() as temp:
            m.save_prepared_cache(markdown, "business",
                                  {url: (image_bytes(), "image/jpeg", ".jpg")}, Path(temp))
            manifest = json.loads((Path(temp) / "manifest.json").read_text("utf-8"))
            filename = manifest["images"][url]["file"]
            (Path(temp) / filename).write_bytes(b"tampered")
            env = {"CONTENT_OS_IMAGE_CACHE_READ": "1", "CONTENT_OS_IMAGE_CACHE_DIR": temp}
            with patch.dict(os.environ, env):
                with self.assertRaisesRegex(RuntimeError, "cache unavailable or tampered"):
                    m.prepare_images(markdown, "business")
            (Path(temp) / "manifest.json").unlink()
            with patch.dict(os.environ, env):
                with self.assertRaisesRegex(RuntimeError, "cache unavailable or tampered"):
                    m.prepare_images(markdown, "business")

    def test_fashion_requires_five_distinct_real_images(self):
        article = "\n".join("![Example](https://example.com/i" + str(i) + ".jpg)" for i in range(4))
        with self.assertRaisesRegex(ValueError, "five distinct"):
            m.prepare_images(article, "fashion")


if __name__ == "__main__":
    unittest.main()
