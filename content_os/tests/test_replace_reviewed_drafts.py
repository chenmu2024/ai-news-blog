import unittest
from content_os.replace_reviewed_drafts import identical, unchanged_draft, prepared, render, PROFILES


class ReplacementTest(unittest.TestCase):
    def setUp(self):
        self.body = '<p>正文&amp;来源</p><img src="http://mmbiz.qpic.cn/mmbiz_jpg/asset/0?from=appmsg">'
        self.article = {'title': '标题', 'content': self.body, 'thumb_media_id': 'cover'}

    def test_roundtrip(self):
        changed = dict(self.article, content=self.body.replace('/0?from=appmsg', '/640'))
        self.assertTrue(identical(changed, '标题', self.body, 'cover'))

    def test_wrong_title(self):
        self.assertFalse(identical(self.article, '另一标题', self.body))

    def test_wrong_body(self):
        changed = dict(self.article, content=self.body.replace('正文', '篡改'))
        self.assertFalse(identical(changed, '标题', self.body))

    def test_missing_image(self):
        self.assertFalse(identical(dict(self.article, content='<p>正文&amp;来源</p>'), '标题', self.body))

    def test_wrong_host_and_cover(self):
        changed = dict(self.article, content=self.body.replace('mmbiz.qpic.cn', 'example.com'))
        self.assertFalse(identical(changed, '标题', self.body))
        self.assertFalse(identical(self.article, '标题', self.body, 'wrong-cover'))

    def test_original_readback_ignores_only_volatile_api_fields(self):
        original = dict(self.article, author="编辑", update_time=111, read_count=2)
        reread = dict(original, update_time=222, read_count=4)
        self.assertTrue(unchanged_draft(original, reread))
        for changed in (
            dict(reread, content=self.body.replace('正文', '已修改')),
            dict(reread, title='另一标题'),
            dict(reread, thumb_media_id='other-cover'),
            dict(reread, author='其他作者'),
        ):
            with self.subTest(changed=changed):
                self.assertFalse(unchanged_draft(original, changed))

    def test_approved_package(self):
        count = 0
        for profile in PROFILES:
            row, md, images, journal = prepared(profile)
            self.assertIn(journal['draft_media_id'], str(journal))
            self.assertEqual(len(images), len(row['images']))
            self.assertIn('style=', render(md))
            count += len(images)
        self.assertEqual(count, 22)
        with self.assertRaises(ValueError):
            prepared('../unknown')


if __name__ == '__main__':
    unittest.main()
