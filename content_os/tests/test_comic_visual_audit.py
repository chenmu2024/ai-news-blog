"""Offline binary comic checks: real files and screen-level duplicates."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from content_os.comic_visual_audit import audit

BASE="https://raw.githubusercontent.com/chenmu2024/ai-news-blog/main/"
DAY="2026-10-15"
PROFILE="business"


class ComicVisualAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.paths=[]
        self.images=[]
        for index in range(5):
            relative=f"content_os/assets/ai-scenes/{PROFILE}/{DAY}/strip-{index}.jpg"
            path=self.root/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            # Different image noise, like five distinct panels in a synthetic
            # fixture. This intentionally does not attest to artistic quality.
            image=Image.effect_noise((700,1050),40+index*20).convert("RGB")
            image.save(path,format="JPEG",quality=91)
            self.paths.append(path)
            self.images.append({"url":BASE+relative,"sha256":"0"*64})
        self.md="<!-- COMIC_PACKAGE "+json.dumps({"images":self.images})+" -->"

    def run_audit(self):
        # Structure/approval checked separately by test_comic_gate. In these
        # tests only the post-structure real-byte image validator is exercised.
        with patch("content_os.comic_visual_audit.check", return_value=[]):
            return audit(PROFILE,DAY,self.md,self.root)

    def test_distinct_mobile_strips_pass_binary_audit(self):
        self.assertEqual(self.run_audit(), [])

    def test_one_pixel_changed_copy_is_detected_as_near_duplicate(self):
        with Image.open(self.paths[0]) as raw:
            copy=raw.convert("RGB")
        copy.putpixel((12,16),(255,0,0))
        copy.save(self.paths[1],format="JPEG",quality=91)
        self.assertTrue(any("near_duplicate_of_1" in x for x in self.run_audit()))

    def test_broken_image_is_rejected(self):
        self.paths[0].write_bytes(b"not a real image"*3000)
        self.assertTrue(any("invalid_or_undecodable_image_bytes" in x for x in self.run_audit()))

    def test_tiny_page_is_rejected(self):
        image=Image.effect_noise((180,200),90).convert("RGB")
        image.save(self.paths[0],format="JPEG",quality=95)
        self.assertTrue(any("unreadable_mobile_dimensions" in x for x in self.run_audit()))

    def test_preview_can_audit_actual_images_without_final_approval(self):
        # Preview mode deliberately skips ONLY the missing approval/editorial
        # attestations; all real image-byte checks remain active.
        with patch("content_os.comic_visual_audit.check", return_value=[
            "comic_user_approval_not_recorded_for_exact_candidate",
            "comic_user_approved_body_hash_mismatch",
            "comic_editorial_and_visual_attestation_incomplete"
        ]):
            self.assertEqual(audit(PROFILE, DAY, self.md, self.root, preview=True), [])
            self.assertNotEqual(audit(PROFILE, DAY, self.md, self.root), [])

    def test_preview_does_not_suppress_missing_file_errors(self):
        with patch("content_os.comic_visual_audit.check", return_value=[
            "comic_user_approval_not_recorded_for_exact_candidate",
            "comic_strip_3_asset_not_persisted"
        ]):
            self.assertIn("comic_strip_3_asset_not_persisted",
                          audit(PROFILE, DAY, self.md, self.root, preview=True))

    def test_old_draft_is_not_subject_to_new_rule(self):
        self.assertEqual(audit(PROFILE,"2026-10-14","no comic",self.root),[])


if __name__ == "__main__":
    unittest.main()
