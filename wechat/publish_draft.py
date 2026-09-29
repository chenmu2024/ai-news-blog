from __future__ import annotations
import hashlib, os, re, sys
from pathlib import Path
from io import BytesIO
import markdown
import requests
from PIL import Image

APP_ID = os.environ["WECHAT_APP_ID"].strip()
APP_SECRET = os.environ["WECHAT_APP_SECRET"].strip()
FIXIE_URL = (os.getenv("FIXIE_URL") or "").strip()
AUTHOR = (os.getenv("WECHAT_AUTHOR") or "陈慕").strip()
ARTICLE = Path(os.getenv("ARTICLE_PATH", "wechat/articles/today.md"))
API = "https://api.weixin.qq.com/cgi-bin"
PROXIES = {"http": FIXIE_URL, "https": FIXIE_URL} if FIXIE_URL else None

def fail(msg):
    print("[ERROR]", msg)
    sys.exit(1)

def token():
    r = requests.get(API + "/token", params={
        "grant_type": "client_credential",
        "appid": APP_ID,
        "secret": APP_SECRET
    }, timeout=30, proxies=PROXIES)
    r.raise_for_status()
    d = r.json()
    if not d.get("access_token"):
        fail("获取 access_token 失败: " + str(d))
    return d["access_token"]

def unwrap(md):
    s = md.strip()
    fence = chr(96) * 3
    if s.startswith(fence + "markdown") and s.endswith(fence):
        return s[len(fence + "markdown"):-len(fence)].strip()
    return md

def title_of(md):
    m = re.search(r"(?m)^#\s+(.+?)\s*$", md)
    if not m:
        fail("缺少一级标题")
    return re.sub(r"[*_]", "", m.group(1)).strip()[:64]

def digest_of(md):
    s = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", md)
    s = re.sub(r"(?m)^#.*$", "", s)
    s = re.sub(r"[*_>#~\[\]()\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:110]

def get_image(url):
    r = requests.get(url, timeout=40, allow_redirects=True)
    r.raise_for_status()
    ct = (r.headers.get("Content-Type") or "").split(";")[0].lower()
    if ct not in ("image/png", "image/jpeg"):
        raise RuntimeError("图片类型不合格: %s -> %s" % (url, ct))

    # Only the WeChat upload goes through Fixie. Compress first to conserve
    # the free proxy bandwidth while keeping article images readable.
    img = Image.open(BytesIO(r.content))
    img.thumbnail((1200, 1200))
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, "white")
        alpha = img.getchannel("A")
        bg.paste(img.convert("RGB"), mask=alpha)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    out = BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue(), "image/jpeg", ".jpg"

def upload_body(tok, content, mime, ext):
    r = requests.post(
        API + "/media/uploadimg",
        params={"access_token": tok},
        files={"media": ("image" + ext, content, mime)},
        timeout=60,
        proxies=PROXIES,
    )
    r.raise_for_status()
    d = r.json()
    if not d.get("url"):
        raise RuntimeError("正文图片上传失败: " + str(d))
    return d["url"]

def upload_cover(tok, content, mime, ext):
    r = requests.post(
        API + "/material/add_material",
        params={"access_token": tok, "type": "image"},
        files={"media": ("cover" + ext, content, mime)},
        timeout=60,
        proxies=PROXIES,
    )
    r.raise_for_status()
    d = r.json()
    if not d.get("media_id"):
        raise RuntimeError("封面上传失败: " + str(d))
    return d["media_id"]

def replace_images(md, tok):
    pat = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")
    cache = {}
    first = [None]

    def repl(m):
        alt, url = m.group(1), m.group(2)
        if url not in cache:
            content, mime, ext = get_image(url)
            cache[url] = upload_body(tok, content, mime, ext)
            if first[0] is None:
                first[0] = (content, mime, ext)
            print("[IMAGE]", url)
        return "![%s](%s)" % (alt, cache[url])

    return pat.sub(repl, md), first[0]

def styled_html(md):
    raw = markdown.markdown(md, extensions=["extra", "fenced_code", "sane_lists"], output_format="html5")
    raw = re.sub(r"<h2>(.*?)</h2>", r'<h2 style="font-size:22px;line-height:1.5;margin:34px 0 16px;font-weight:700;">\1</h2>', raw, flags=re.S)
    raw = re.sub(r"<h3>(.*?)</h3>", r'<h3 style="font-size:18px;line-height:1.6;margin:28px 0 12px;font-weight:700;">\1</h3>', raw, flags=re.S)
    raw = re.sub(r"<p>(.*?)</p>", r'<p style="font-size:16px;line-height:1.95;margin:14px 0;color:#222;">\1</p>', raw, flags=re.S)
    raw = re.sub(r"<blockquote>(.*?)</blockquote>", r'<blockquote style="margin:18px 0;padding:12px 16px;border-left:4px solid #999;background:#f7f7f7;color:#555;">\1</blockquote>', raw, flags=re.S)
    raw = re.sub(r'<img ([^>]*?)src="([^"]+)"([^>]*)>', r'<img \1src="\2"\3 style="max-width:100%;height:auto;display:block;margin:18px auto;" />', raw, flags=re.S)
    raw = raw.replace("<hr />", '<hr style="border:none;border-top:1px solid #e5e5e5;margin:30px 0;" />')
    return '<section style="font-size:16px;line-height:1.95;color:#222;word-break:break-word;">' + raw + "</section>"

def create_draft(tok, title, digest, body, cover_id):
    payload = {"articles": [{
        "title": title,
        "author": AUTHOR[:16],
        "digest": digest[:120],
        "content": body,
        "content_source_url": "",
        "thumb_media_id": cover_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0
    }]}
    r = requests.post(API + "/draft/add", params={"access_token": tok}, json=payload, timeout=60, proxies=PROXIES)
    r.raise_for_status()
    d = r.json()
    if not d.get("media_id"):
        fail("创建草稿失败: " + str(d))
    return d["media_id"]

def main():
    if not ARTICLE.exists():
        fail("文章不存在: " + str(ARTICLE))
    md = unwrap(ARTICLE.read_text(encoding="utf-8"))
    title = title_of(md)
    digest = digest_of(md)
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()
    print("[ARTICLE]", title)
    print("[PROXY]", "Fixie enabled" if PROXIES else "Direct connection")
    print("[SHA256]", sha)

    tok = token()
    body_md = re.sub(r"(?m)^#\s+.+?\s*$", "", md, count=1).lstrip()
    body_md, cover = replace_images(body_md, tok)
    if not cover:
        fail("文章没有可用 PNG/JPEG 图片，无法创建公众号封面。")
    cover_id = upload_cover(tok, cover[0], cover[1], cover[2])
    media_id = create_draft(tok, title, digest, styled_html(body_md), cover_id)
    print("[SUCCESS] 已保存到微信公众号草稿箱")
    print("[SAFE] 未调用任何正式发布接口")
    print("[DRAFT_MEDIA_ID]", media_id)

if __name__ == "__main__":
    main()
