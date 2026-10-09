"""Offline reliability regressions; no WeChat calls or network requests."""
import io
import json
import sys
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
        self.assertTrue(out[url][0].startswith(b"\\xff\\xd8"))

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

    def test_only_public_https_hosts(self):
        for url in ["http://example.com/a.jpg", "https://localhost/a.jpg",
                    "https://127.0.0.1/a.jpg", "https://10.0.0.1/a.jpg"]:
            self.assertFalse(m.public_https(url))
        self.assertTrue(m.public_https("https://images.pexels.com/p.jpg"))

    def test_fashion_requires_five_distinct_real_images(self):
        article = "\n".join("![Example](https://example.com/i" + str(i) + ".jpg)" for i in range(4))
        with self.assertRaisesRegex(ValueError, "five distinct"):
            m.prepare_images(article, "fashion")


if __name__ == "__main__":
    unittest.main()
