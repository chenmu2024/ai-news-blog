from __future__ import annotations
import hashlib, json, os, re, sys, subprocess, time
from pathlib import Path
from urllib.parse import urlparse
from io import BytesIO
import markdown
import requests
from PIL import Image, ImageDraw, ImageFont

# Shared zero-cost preflight; no WeChat API call until every source image is staged.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content_os.image_resilience import prepare_images, strip_image_backup_notes
from content_os.public_draft_contract import verify_and_record
from content_os.draft_journal import reserve as reserve_draft_add, confirm as confirm_draft_add
_PREPARED_IMAGES = {}


APP_ID = os.environ["WECHAT_APP_ID"].strip()
APP_SECRET = os.environ["WECHAT_APP_SECRET"].strip()
PROXY_URL = (os.getenv("PROXY_URL") or os.getenv("FIXIE_URL") or "").strip()
AUTHOR = (os.getenv("WECHAT_AUTHOR") or "陈慕").strip()
ARTICLE = Path(os.getenv("ARTICLE_PATH", "parenting/articles/today.md"))
API = "https://api.weixin.qq.com/cgi-bin"
# bridge-test-trigger
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

def proxy_variants():
    if not PROXY_URL:
        return [None]
    # Use the exact Webshare direct proxy configured in PROXY_URL.
    # This keeps the WeChat API source IP identical to the allowlisted IP.
    return [{"http": PROXY_URL, "https": PROXY_URL}]

def request_with_proxy(method, url, **kwargs):
    last = None
    for idx, proxies in enumerate(proxy_variants(), start=1):
        try:
            r = requests.request(method, url, proxies=proxies, **kwargs)
            r.raise_for_status()
            if idx == 1 and PROXY_URL:
                print("[PROXY] Direct static proxy connected")
            return r
        except Exception as e:
            last = e
            if idx < len(proxy_variants()):
                print(f"[PROXY] Mode {idx} failed; trying fallback")
                continue
            raise last

def fail(msg):
    print("[ERROR]", msg)
    sys.exit(1)

def token():
    r = request_with_proxy("GET", API + "/token", params={
        "grant_type": "client_credential",
        "appid": APP_ID,
        "secret": APP_SECRET
    }, timeout=30)
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

def strip_internal_notes(md):
    # Remove editor-facing production notes that must never appear to readers.
    headings = (
        "数据核验说明",
        "图片说明",
        "配图说明",
        "发布说明",
        "编辑说明",
        "内部备注",
        "来源核验说明",
    )
    names = "|".join(re.escape(x) for x in headings)
    md = re.sub(
        rf"(?ms)^##+\s*(?:{names})\s*$.*?(?=^##+\s|\Z)",
        "",
        md,
    )
    # Remove image-placement placeholders used during drafting.
    md = re.sub(r"(?m)^>\s*配图建议：.*(?:\n|$)", "", md)
    public_meta = ("资料来源", "图片来源", "参考资料", "参考来源", "核验说明", "编辑说明", "发布说明")
    names2 = "|".join(re.escape(x) for x in public_meta)
    md = re.sub(rf"(?ms)^##+\s*(?:{names2})\s*$.*?(?=^##+\s|\Z)", "", md)
    md = re.sub(rf"(?m)^\s*(?:\*\*)?(?:{names2})[：:].*?(?:\*\*)?\s*$", "", md)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"

def title_of(md):
    m = re.search(r"(?m)^#\s+(.+?)\s*$", md)
    if not m:
        fail("缺少一级标题")
    return re.sub(r"[*_]", "", m.group(1)).strip()

def wechat_safe_title(title):
    # Current draft API documentation uses a 32-character title ceiling.
    # Keep the Markdown H1 untouched; only shorten the WeChat title field.
    if len(title) <= 32:
        return title
    return title[:31].rstrip("，。！？：；、 ") + "…"

def digest_of(md):
    s = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", md)
    s = re.sub(r"(?m)^#.*$", "", s)
    s = re.sub(r"[*_>#~\[\]()\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:110]

def font_file(family="Noto Sans CJK SC"):
    try:
        path = subprocess.check_output(
            ["fc-match", "-f", "%{file}", family],
            text=True,
        ).strip()
        if path:
            return path
    except Exception:
        pass
    for p in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(p).exists():
            return p
    raise RuntimeError("找不到可用字体")

def font(size, bold=False):
    family = "Noto Sans CJK SC:style=Bold" if bold else "Noto Sans CJK SC"
    return ImageFont.truetype(font_file(family), size)

def wrap_text(draw, text, ft, max_width):
    lines, line = [], ""
    for ch in str(text):
        trial = line + ch
        if draw.textlength(trial, font=ft) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines

def make_fallback_cover(title):
    # WeChat needs a thumb_media_id even when the article deliberately has
    # no body images. Generate a relevant editorial cover locally instead
    # of failing or inserting an unrelated logo/stock image.
    W, H = 1200, 510
    bg = (248, 247, 241)
    panel = (255, 253, 248)
    text = (20, 27, 39)
    muted = (94, 105, 122)
    accent = (104, 134, 102)
    line = (226, 232, 240)

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((28, 28, W-28, H-28), radius=30, fill=panel, outline=line, width=2)
    d.rounded_rectangle((72, 66, 270, 112), radius=23, fill=(235, 242, 255))
    d.text((96, 75), "陈慕育儿", font=font(24, True), fill=accent)

    title_font = font(52, True)
    lines = wrap_text(d, title, title_font, W-160)[:3]
    y = 150 if len(lines) <= 2 else 132
    for i, ln in enumerate(lines):
        d.text((78, y + i*67), ln, font=title_font, fill=text)

    divider_y = 352 if len(lines) <= 2 else 378
    d.line((78, divider_y, W-78, divider_y), fill=line, width=2)
    d.rectangle((78, divider_y-1, 250, divider_y+1), fill=accent)
    d.text((78, divider_y+32), "陈慕｜孩子 · 父母 · 家庭 · 成长", font=font(27), fill=muted)
    print("[FALLBACK_COVER] generated locally")
    return image_to_jpeg(img)

def image_to_jpeg(img):
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = BytesIO()
    img.save(out, format="JPEG", quality=88, optimize=True)
    return out.getvalue(), "image/jpeg", ".jpg"

WECHAT_CARD_RE = re.compile(r"<!--\s*WECHAT_CARD\s+(.+?)\s*-->", re.S)

def make_info_card(spec):
    W = 1080
    title = str(spec.get("title") or "育儿与家庭教育")
    subtitle = str(spec.get("subtitle") or "")
    items = spec.get("items") or []
    if not isinstance(items, list):
        items = []
    items = items[:6]

    bg = (248, 246, 241)
    panel = (255, 255, 255)
    ink = (24, 31, 43)
    muted = (92, 103, 121)
    accent = (169, 112, 53)
    accent2 = (170, 132, 94)
    border = (225, 231, 239)

    row_h = 188
    H = 315 + max(1, len(items)) * row_h + 80
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    d.rounded_rectangle((32, 32, W-32, H-32), radius=30, fill=panel, outline=border, width=2)
    d.rounded_rectangle((70, 58, 300, 104), radius=22, fill=(235, 242, 255))
    d.text((92, 68), "陈慕 · 陈慕育儿", font=font(22, True), fill=accent)

    d.text((70, 128), title, font=font(46, True), fill=ink)
    if subtitle:
        sy = 190
        for i, ln in enumerate(wrap_text(d, subtitle, font(25), W-140)[:2]):
            d.text((72, sy+i*34), ln, font=font(25), fill=muted)

    divider_y = 250
    d.line((70, divider_y, W-70, divider_y), fill=border, width=2)
    d.rectangle((70, divider_y-1, 250, divider_y+1), fill=accent)

    y = 282
    for idx, raw in enumerate(items, start=1):
        if isinstance(raw, str):
            name, lead, detail = raw, "", ""
        else:
            name = str(raw.get("name") or f"第{idx}点")
            lead = str(raw.get("lead") or "")
            detail = str(raw.get("detail") or "")
        top = y
        bottom = y + row_h - 22

        d.rounded_rectangle((58, top, W-58, bottom), radius=24, fill=(249, 251, 254), outline=border, width=2)
        badge = accent if idx % 2 else accent2
        d.rounded_rectangle((82, top+28, 160, top+106), radius=20, fill=badge)

        num = f"{idx:02d}"
        nf = font(28, True)
        box = d.textbbox((0, 0), num, font=nf)
        d.text((121-(box[2]-box[0])/2, top+51), num, font=nf, fill=(255,255,255))

        d.text((194, top+24), name, font=font(32, True), fill=ink)

        if lead:
            lead_lines = wrap_text(d, lead, font(24, True), W-300)[:2]
            for j, ln in enumerate(lead_lines):
                d.text((194, top+70+j*32), ln, font=font(24, True), fill=accent)
        else:
            lead_lines = []

        if detail:
            detail_y = top + (132 if lead_lines else 80)
            for j, ln in enumerate(wrap_text(d, detail, font(22), W-300)[:2]):
                if detail_y + j*30 < bottom - 10:
                    d.text((194, detail_y+j*30), ln, font=font(22), fill=muted)

        y += row_h

    d.text((70, H-58), "孩子 · 父母 · 家庭 · 成长", font=font(20), fill=(132, 142, 158))
    return image_to_jpeg(img)

def replace_cards(md, tok):
    count = [0]

    def repl(m):
        try:
            spec = json.loads(m.group(1))
        except Exception as e:
            raise RuntimeError("WECHAT_CARD JSON格式错误: " + str(e))
        content, mime, ext = make_info_card(spec)
        url = upload_body(tok, content, mime, ext)
        count[0] += 1
        return f'<img src="{url}" alt="信息图" />'

    out = WECHAT_CARD_RE.sub(repl, md)
    if count[0]:
        print("[WECHAT_CARDS]", count[0])
    return out, count[0]

def get_image(url):
    # Bytes were decoded and converted to JPEG before the first WeChat API request.
    if url not in _PREPARED_IMAGES:
        raise RuntimeError("Image was not prepared by Content OS preflight: " + url)
    return _PREPARED_IMAGES[url]

def upload_body(tok, content, mime, ext):
    r = request_with_proxy(
        "POST",
        API + "/media/uploadimg",
        params={"access_token": tok},
        files={"media": ("image" + ext, content, mime)},
        timeout=60,
    )
    d = r.json()
    if not d.get("url"):
        raise RuntimeError("正文图片上传失败: " + str(d))
    return d["url"]

def upload_cover(tok, content, mime, ext):
    r = request_with_proxy(
        "POST",
        API + "/material/add_material",
        params={"access_token": tok, "type": "image"},
        files={"media": ("cover" + ext, content, mime)},
        timeout=60,
    )
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

def get_draft(tok, media_id):
    r = request_with_proxy(
        "POST",
        API + "/draft/get",
        params={"access_token": tok},
        data=json.dumps({"media_id": media_id}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=60,
    )
    d = r.json()
    if d.get("errcode"):
        fail("读取草稿失败: " + str(d))
    return d

def verify_public_draft(tok, media_id):
    d = get_draft(tok, media_id)
    items = d.get("news_item") or []
    if not items:
        fail("微信草稿回读为空，无法验证公开正文")
    html = "\n".join(str(x.get("content") or "") for x in items if isinstance(x, dict))
    forbidden = ["资料来源", "图片来源", "核验说明", "编辑说明", "发布说明", "内部备注", "Content-Type", "Markdown"]
    leaked = [x for x in forbidden if x in html]
    if leaked:
        fail("微信公开草稿仍包含内部生产信息: " + ", ".join(leaked))
    print("[PUBLIC_COPY_VERIFY] PASS")

def create_draft(tok, title, body, cover_id):
    payload = {"articles": [{
        "article_type": "news",
        "title": title,
        "author": AUTHOR[:16],
        "content": body,
        "content_source_url": "",
        "thumb_media_id": cover_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0
    }]}
    post_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    # Durable intent must be committed to GitHub BEFORE the non-idempotent
    # WeChat draft/add API. Unknown outcomes must never be blindly retried.
    reserve_draft_add("parenting", ARTICLE, title)
    r = request_with_proxy(
        "POST",
        API + "/draft/add",
        params={"access_token": tok},
        data=post_data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=60,
    )
    d = r.json()
    if not d.get("media_id"):
        fail("创建草稿失败: " + str(d))
    confirm_draft_add("parenting", ARTICLE, d["media_id"])
    return d["media_id"]

def main():
    if not ARTICLE.exists():
        fail("文章不存在: " + str(ARTICLE))
    md = strip_image_backup_notes(strip_internal_notes(unwrap(ARTICLE.read_text(encoding="utf-8"))), profile="parenting")
    title = title_of(md)
    api_title = wechat_safe_title(title)
    digest = digest_of(md)
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()
    print("[ARTICLE]", title)
    if api_title != title:
        print("[WECHAT_TITLE]", api_title)
    print("[PROXY]", "Static proxy enabled" if PROXIES else "Direct connection")
    print("[SHA256]", sha)

    # Failure here is safe: neither media/uploadimg nor draft/add was called.
    _PREPARED_IMAGES.clear()
    _PREPARED_IMAGES.update(prepare_images(ARTICLE.read_text(encoding="utf-8"), profile="parenting"))
    print("[IMAGE_PREFLIGHT] staged", len(_PREPARED_IMAGES), "real source images")
    tok = token()
    body_md = re.sub(r"(?m)^#\s+.+?\s*$", "", md, count=1).lstrip()
    body_md, _card_count = replace_cards(body_md, tok)
    body_md, cover = replace_images(body_md, tok)
    if not cover:
        cover = make_fallback_cover(api_title)
    cover_id = upload_cover(tok, cover[0], cover[1], cover[2])
    public_html = styled_html(body_md)
    media_id = create_draft(tok, api_title, public_html, cover_id)
    # Read-only verification; confirmed journal prevents duplicate draft/add.
    verify_and_record("parenting", ARTICLE, api_title, media_id, public_html,
                      tok, request_with_proxy, API)
    verify_public_draft(tok, media_id)
    print("[SUCCESS] 已保存到微信公众号草稿箱")
    print("[SAFE] 未调用任何正式发布接口")
    print("[DRAFT_MEDIA_ID]", media_id)

if __name__ == "__main__":
    main()
