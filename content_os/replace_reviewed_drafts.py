"""Replace explicitly authorized reviewed drafts by confirmed ID, never add/send.

The original archive/journal stay immutable. Persist a full backup and intent
before the single update call; reruns only read back an ambiguous prior attempt.
"""
import base64
import hashlib
from html.parser import HTMLParser
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import markdown
from PIL import Image
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content_os.draft_journal import _environment, _get, _request, _endpoint
from content_os.public_draft_contract import image_sources

DAY = '2026-10-13'
BASE = Path('content_os/revisions') / DAY
PROFILES = ('qiezhi', 'wechat', 'business', 'zizhitongjian', 'parenting', 'jingyun', 'fashion')
IMAGE = re.compile(r'!\[([^\]]*)\]\((assets/[^)\s]+)\)')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def text(body):
    parser = Text()
    parser.feed(body)
    return re.sub(r'\s+', '', ''.join(parser.parts))


def image_key(url):
    parsed = urlsplit(url)
    if parsed.hostname != 'mmbiz.qpic.cn':
        raise RuntimeError('Image is not hosted by WeChat')
    return parsed.path.rsplit('/', 1)[0]


def identical(article, title, body, cover=None):
    try:
        return (article.get('title') == title
                and text(article.get('content', '')) == text(body)
                and [image_key(x) for x in image_sources(article.get('content', ''))]
                == [image_key(x) for x in image_sources(body)]
                and (cover is None or article.get('thumb_media_id') == cover))
    except (ValueError, RuntimeError):
        return False


def unchanged_draft(before, after):
    """Compare stable visible content; ignore volatile WeChat response fields."""
    return (identical(after, before.get('title'), before.get('content', ''),
                      before.get('thumb_media_id'))
            and after.get('author') == before.get('author'))


def prepared(profile):
    if profile not in PROFILES:
        raise ValueError('Unknown profile')
    auth = json.loads((BASE / 'authorization.json').read_text('utf-8'))
    if (auth['operation'] != 'in_place_draft_update' or auth['date'] != DAY
            or auth['profiles'] != list(PROFILES)
            or sha((BASE / 'manifest.json').read_bytes()) != auth['manifest_sha256']
            or sha((BASE / '检查结果.json').read_bytes()) != auth['review_sha256']):
        raise RuntimeError('Authorization/review mismatch')
    manifest = json.loads((BASE / 'manifest.json').read_text('utf-8'))
    row = next(x for x in manifest['articles'] if x['profile'] == profile)
    raw = (BASE / (profile + '.md')).read_bytes()
    md = raw.decode('utf-8')
    if sha(raw) != row['markdown_sha256'] or md.splitlines()[0] != '# ' + row['title']:
        raise RuntimeError('Reviewed article SHA/title mismatch')
    matches = IMAGE.findall(md)
    if matches != [tuple(x) for x in row['images']]:
        raise RuntimeError('Reviewed image order mismatch')
    review = json.loads((BASE / '检查结果.json').read_text('utf-8'))
    if (review['articles'] != 7 or review['images'] != 22
            or any(review[k] != 0 for k in ('broken_images', 'horizontal_overflow', 'page_errors'))):
        raise RuntimeError('Preview review failed')
    assets = {x['path']: x for x in review['assets']}
    images = {}
    for _, name in matches:
        path = BASE / name
        if path.resolve().parent != (BASE / 'assets').resolve():
            raise RuntimeError('Image path escapes approved assets')
        data = path.read_bytes()
        if sha(data) != assets[name]['sha256']:
            raise RuntimeError('Reviewed image SHA mismatch')
        with Image.open(BytesIO(data)) as im:
            im.load()
            out = BytesIO()
            im.convert('RGB').save(out, format='JPEG', quality=92, optimize=True)
            images[name] = out.getvalue()
    journal_path = f'{profile}/status/draft-attempts/{DAY}.json'
    journal = json.loads(Path(journal_path).read_text('utf-8'))
    original = Path(profile) / 'archive' / (DAY + '.md')
    if (journal.get('state') != 'confirmed' or journal.get('profile') != profile
            or journal.get('article_path') != original.as_posix()
            or journal.get('article_sha256') != sha(original.read_bytes().replace(b'\r\n', b'\n'))
            or not journal.get('draft_media_id')):
        raise RuntimeError('Original confirmed ID/archive binding failed')
    return row, md.split('\n', 1)[1], images, journal


def render(md):
    body = markdown.markdown(md, extensions=['extra', 'sane_lists'], output_format='html5')
    styles = {
        'p': 'font-size:16px;line-height:1.95;margin:18px 0;color:#222;',
        'h2': 'font-size:22px;line-height:1.5;margin:32px 0 16px;',
        'h3': 'font-size:18px;line-height:1.6;margin:26px 0 12px;',
        'table': 'width:100%;border-collapse:collapse;font-size:14px;line-height:1.7;',
        'th': 'border:1px solid #ddd;padding:8px;background:#f4f4f4;text-align:left;',
        'td': 'border:1px solid #ddd;padding:8px;vertical-align:top;',
        'blockquote': 'border-left:3px solid #999;margin:20px 0;padding:0 14px;',
    }
    for tag, style in styles.items():
        body = body.replace('<' + tag + '>', '<' + tag + ' style="' + style + '">')
    body = re.sub(r'<img ', '<img style="max-width:100%;height:auto;display:block;margin:22px auto;" ', body)
    return '<section style="font-size:16px;line-height:1.95;word-break:break-word;">' + body + '</section>'


def persist(token, repo, path, value):
    _, old_sha = _get(token, repo, path)
    payload = {'message': 'wechat: record reviewed in-place replacement', 'branch': 'main',
               'content': base64.b64encode((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()).decode()}
    if old_sha:
        payload['sha'] = old_sha
    _request('PUT', _endpoint(repo, path), token, payload)


def main(profile):
    row, md, images, original = prepared(profile)
    github_token, repo, run_id = _environment()
    receipt_path = f'{profile}/status/revisions/{DAY}.json'
    previous, _ = _get(github_token, repo, receipt_path)
    media_id = original['draft_media_id']
    proxy = os.environ['PROXY_URL'].strip()
    if not proxy:
        raise RuntimeError('Static WeChat proxy required')
    session = requests.Session()
    session.trust_env = False
    session.proxies = {'http': proxy, 'https': proxy}

    def api(endpoint, **kwargs):
        # Exactly one request, especially for draft/update. Never retry a write.
        response = session.request('GET' if endpoint == '/token' else 'POST',
                                   'https://api.weixin.qq.com/cgi-bin' + endpoint,
                                   timeout=90, **kwargs)
        response.raise_for_status()
        result = json.loads(response.content.decode('utf-8'))
        if result.get('errcode', 0) != 0:
            raise RuntimeError(f'WeChat {endpoint} error code {result["errcode"]}')
        return result

    token = api('/token', params={'grant_type': 'client_credential',
                                 'appid': os.environ['WECHAT_APP_ID'].strip(),
                                 'secret': os.environ['WECHAT_APP_SECRET'].strip()})['access_token']
    params = {'access_token': token}

    def current():
        articles = api('/draft/get', params=params, json={'media_id': media_id}).get('news_item') or []
        if len(articles) != 1:
            raise RuntimeError('Original media ID must resolve to precisely one article')
        return articles[0]

    saved = current()
    if previous:
        if (previous.get('draft_media_id') != media_id
                or previous.get('revision_sha256') != row['markdown_sha256']):
            raise RuntimeError('Prior revision conflicts with this authorization')
        if not identical(saved, row['title'], previous['expected_html'], previous['expected_cover']):
            raise RuntimeError('Prior attempt needs investigation; refusing automatic update retry')
        receipt = previous
    else:
        if saved.get('title') != original['title']:
            raise RuntimeError('Original draft title changed; refuse overwrite')
        old_readback = json.loads(Path(f'{profile}/status/draft-readback/{DAY}.json').read_text('utf-8'))
        if (old_readback.get('draft_media_id') != media_id
                or old_readback.get('article_sha256') != original['article_sha256']
                or old_readback.get('readback_body_sha256') != sha(saved.get('content', '').encode('utf-8'))):
            raise RuntimeError('Original draft body changed since confirmed readback; refuse overwrite')
        expected_urls = original['expected_inline_urls']
        if [image_key(x) for x in image_sources(saved.get('content', ''))] != [image_key(x) for x in expected_urls]:
            raise RuntimeError('Original draft body images changed; refuse overwrite')
        urls = {}
        for name, data in images.items():
            urls[name] = api('/media/uploadimg', params=params,
                             files={'media': ('image.jpg', data, 'image/jpeg')})['url']
            image_key(urls[name])
        cover = api('/material/add_material', params={**params, 'type': 'image'},
                    files={'media': ('cover.jpg', next(iter(images.values())), 'image/jpeg')})['media_id']
        body = render(IMAGE.sub(lambda m: '![' + m[1] + '](' + urls[m[2]] + ')', md))
        if len(image_sources(body)) != len(row['images']):
            raise RuntimeError('Rendered image count mismatch')
        # Verify the original has not been edited during uploads.
        if not unchanged_draft(saved, current()):
            raise RuntimeError('Original draft visible content changed while preparing replacement')
        receipt = {'state': 'attempted', 'status': 'pending', 'operation': 'in_place_draft_update',
                   'original_article_path': original['article_path'], 'original_article_sha256': original['article_sha256'],
                   'revision_path': (BASE / (profile + '.md')).as_posix(),
                   'revision_title': row['title'], 'revision_sha256': row['markdown_sha256'],
                   'draft_media_id': media_id, 'workflow_run_id': run_id,
                   'original_backup': saved, 'expected_html': body, 'expected_cover': cover}
        persist(github_token, repo, receipt_path, receipt)
        update = {k: saved[k] for k in ('author', 'need_open_comment', 'only_fans_can_comment') if k in saved}
        update.update(article_type='news', title=row['title'], content=body,
                      thumb_media_id=cover, content_source_url='', digest=text(body)[:110])
        result = api('/draft/update', params=params,
                     data=json.dumps({'media_id': media_id, 'index': 0, 'articles': update}, ensure_ascii=False).encode('utf-8'),
                     headers={'Content-Type': 'application/json; charset=utf-8'})
        if result.get('errcode') != 0:
            raise RuntimeError('Missing explicit update acknowledgement')
        saved = current()
        if not identical(saved, row['title'], body, cover):
            raise RuntimeError('Replacement readback differs from reviewed title/body/images/cover')
    receipt.update(state='confirmed', status='success', verified_images=len(row['images']),
                   verified_title=saved['title'], verified_text_sha256=sha(text(saved['content']).encode('utf-8')))
    persist(github_token, repo, receipt_path, receipt)
    print(f'[VERIFIED] {profile}: original media_id retained; {len(row["images"])} images; {row["title"]}')


if __name__ == '__main__':
    try:
        main(sys.argv[1])
    except Exception as exc:
        # Network exceptions can embed token-bearing URLs or proxy credentials.
        print('[FAILED]', type(exc).__name__, str(exc) if isinstance(exc, (RuntimeError, ValueError, KeyError)) else 'Request or file operation failed; inspect durable receipt before retry')
        sys.exit(1)
