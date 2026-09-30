from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import markdown
import requests
from PIL import Image, ImageDraw, ImageFont

APP_ID = os.environ["WECHAT_APP_ID"].strip()
APP_SECRET = os.environ["WECHAT_APP_SECRET"].strip()
PROXY_URL = (os.getenv("PROXY_URL") or "").strip()
AUTHOR = (os.getenv("WECHAT_AUTHOR") or "且知").strip()
ARTICLE = Path(os.getenv("ARTICLE_PATH", "qiezhi/articles/today.md"))
STATUS_PATH = Path(os.getenv("STATUS_PATH", "qiezhi/status/latest.json"))
WECHAT_API = "https://api.weixin.qq.com/cgi-bin"
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

CARD_RE = re.compile(r"<!--\s*QIEZHI_CARD\s+(.+?)\s*-->", re.S)

BG = (247, 241, 229)
PANEL = (251, 248, 240)
RED = (145, 34, 25)
DARK_RED = (111, 24, 18)
GOLD = (184, 146, 72)
TEXT = (42, 38, 34)
MUTED = (100, 92, 84)
LINE = (224, 212, 190)

def fail(msg):
    print("[ERROR]", msg)
    sys.exit(1)

def proxy_variants():
    if not PROXY_URL:
        return [None]
    return [{"http": PROXY_URL, "https": PROXY_URL}]

def request_wechat(method, url, **kwargs):
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
    raise last

def token():
    r = request_wechat(
        "GET",
        WECHAT_API + "/token",
        params={"grant_type": "client_credential", "appid": APP_ID, "secret": APP_SECRET},
        timeout=30,
    )
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
    headings = ("数据核验说明", "图片说明", "配图说明", "发布说明", "编辑说明", "内部备注", "来源核验说明", "生成说明")
    names = "|".join(re.escape(x) for x in headings)
    md = re.sub(rf"(?ms)^##+\s*(?:{names})\s*$.*?(?=^##+\s|\Z)", "", md)
    md = re.sub(r"(?m)^>\s*配图建议：.*(?:\n|$)", "", md)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"

def title_of(md):
    m = re.search(r"(?m)^#\s+(.+?)\s*$", md)
    if not m:
        fail("缺少一级标题")
    return re.sub(r"[*_]", "", m.group(1)).strip()

def wechat_safe_title(title):
    if len(title) <= 32:
        return title
    return title[:31].rstrip("，。！？：；、 ") + "…"

def font_file(family):
    try:
        return subprocess.check_output(["fc-match", "-f", "%{file}", family], text=True).strip()
    except Exception:
        return "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

def F(size, bold=False, serif=False):
    family = "Noto Serif CJK SC" if serif else ("Noto Sans CJK SC:style=Bold" if bold else "Noto Sans CJK SC")
    return ImageFont.truetype(font_file(family), size)

def wrap(draw, text, font, max_width):
    text = str(text or "").strip()
    if not text:
        return []
    out, line = [], ""
    for ch in text:
        trial = line + ch
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                out.append(line)
            line = ch
    if line:
        out.append(line)
    return out

def center_text(draw, y, text, font, fill, width):
    box = draw.textbbox((0, 0), text, font=font)
    tw = box[2] - box[0]
    draw.text(((width - tw) / 2, y), text, font=font, fill=fill)

def draw_cover(spec):
    W, H = 1200, 510
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((28, 28, W-28, H-28), radius=30, fill=PANEL, outline=LINE, width=2)
    d.rectangle((28, 28, 42, H-28), fill=RED)
    title = str(spec.get("title") or "且知")
    subtitle = str(spec.get("subtitle") or "")
    kicker = str(spec.get("kicker") or "毛选方法论")
    center_text(d, 70, kicker, F(34, bold=True), GOLD, W)
    for i, line in enumerate(wrap(d, title, F(62, bold=True, serif=True), W-170)[:2]):
        center_text(d, 132 + i*78, line, F(62, bold=True, serif=True), DARK_RED, W)
    d.line((390, 330, 810, 330), fill=GOLD, width=3)
    if subtitle:
        for i, line in enumerate(wrap(d, subtitle, F(30), W-180)[:2]):
            center_text(d, 360 + i*42, line, F(30), MUTED, W)
    return img

def draw_card(spec):
    W = 1080
    title = str(spec.get("title") or "且知")
    subtitle = str(spec.get("subtitle") or "")
    items = spec.get("items") or []
    if not isinstance(items, list):
        items = []
    items = items[:6]
    row_h = 210
    H = 300 + max(1, len(items))*row_h + 90
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((70, 52), title, font=F(48, bold=True, serif=True), fill=DARK_RED)
    if subtitle:
        for i, line in enumerate(wrap(d, subtitle, F(27), W-140)[:2]):
            d.text((72, 118 + i*38), line, font=F(27), fill=MUTED)
    d.line((72, 205, W-72, 205), fill=GOLD, width=3)
    y = 245
    for idx, raw in enumerate(items, start=1):
        if isinstance(raw, str):
            name, lead, detail = raw, "", ""
        else:
            name = str(raw.get("name") or f"第{idx}点")
            lead = str(raw.get("lead") or "")
            detail = str(raw.get("detail") or "")
        top = y
        bottom = y + row_h - 24
        d.rounded_rectangle((56, top, W-56, bottom), radius=24, fill=PANEL, outline=LINE, width=2)
        d.rounded_rectangle((76, top+28, 176, top+128), radius=22, fill=RED if idx % 2 else GOLD)
        num = f"{idx:02d}"
        box = d.textbbox((0,0), num, font=F(34, bold=True))
        d.text((126-(box[2]-box[0])/2, top+56), num, font=F(34, bold=True), fill=(255,255,255))
        d.text((212, top+26), name, font=F(36, bold=True, serif=True), fill=TEXT)
        if lead:
            lead_lines = wrap(d, lead, F(27, bold=True), W-310)[:2]
            for j, line in enumerate(lead_lines):
                d.text((212, top+80+j*38), line, font=F(27, bold=True), fill=RED)
        if detail:
            detail_y = top + (158 if lead else 98)
            for j, line in enumerate(wrap(d, detail, F(24), W-310)[:2]):
                if detail_y + j*34 < bottom - 12:
                    d.text((212, detail_y+j*34), line, font=F(24), fill=MUTED)
        y += row_h
    d.text((70, H-58), "且知｜把大历史拆成小日常，把大战略拆成小习惯", font=F(22), fill=(140,128,112))
    return img

def image_bytes(img):
    out = BytesIO()
    img.save(out, format="JPEG", quality=88, optimize=True)
    return out.getvalue(), "image/jpeg", ".jpg"

def upload_body(tok, content, mime, ext):
    r = request_wechat("POST", WECHAT_API + "/media/uploadimg", params={"access_token": tok}, files={"media": ("image" + ext, content, mime)}, timeout=90)
    d = r.json()
    if not d.get("url"):
        raise RuntimeError("正文图片上传失败: " + str(d))
    return d["url"]

def upload_cover(tok, content, mime, ext):
    r = request_wechat("POST", WECHAT_API + "/material/add_material", params={"access_token": tok, "type": "image"}, files={"media": ("cover" + ext, content, mime)}, timeout=90)
    d = r.json()
    if not d.get("media_id"):
        raise RuntimeError("封面上传失败: " + str(d))
    return d["media_id"]

def render_and_replace(md, tok):
    cover_id = [None]
    count = [0]
    def repl(m):
        try:
            spec = json.loads(m.group(1))
        except Exception as e:
            raise RuntimeError("QIEZHI_CARD JSON格式错误: " + str(e))
        role = str(spec.get("role") or "inline").lower()
        img = draw_cover(spec) if role == "cover" else draw_card(spec)
        content, mime, ext = image_bytes(img)
        count[0] += 1
        if role == "cover":
            if cover_id[0] is None:
                cover_id[0] = upload_cover(tok, content, mime, ext)
            return ""
        url = upload_body(tok, content, mime, ext)
        if cover_id[0] is None:
            cover_id[0] = upload_cover(tok, content, mime, ext)
        return f"![且知配图]({url})"
    out = CARD_RE.sub(repl, md)
    if count[0] == 0:
        fail("文章没有 QIEZHI_CARD 标记，无法生成配图。")
    if not cover_id[0]:
        fail("没有可用封面图。")
    print("[CARDS]", count[0])
    return out, cover_id[0]

def styled_html(md):
    raw = markdown.markdown(md, extensions=["extra", "fenced_code", "sane_lists"], output_format="html5")
    raw = re.sub(r"<h2>(.*?)</h2>", r'<h2 style="font-size:22px;line-height:1.55;margin:36px 0 16px;font-weight:700;color:#8f1d14;">\1</h2>', raw, flags=re.S)
    raw = re.sub(r"<h3>(.*?)</h3>", r'<h3 style="font-size:18px;line-height:1.6;margin:28px 0 12px;font-weight:700;color:#222;">\1</h3>', raw, flags=re.S)
    raw = re.sub(r"<p>(.*?)</p>", r'<p style="font-size:16px;line-height:1.95;margin:14px 0;color:#222;">\1</p>', raw, flags=re.S)
    raw = re.sub(r"<blockquote>(.*?)</blockquote>", r'<blockquote style="margin:20px 0;padding:14px 18px;border-left:4px solid #a62117;background:#fbf7ef;color:#555;">\1</blockquote>', raw, flags=re.S)
    raw = re.sub(r'<img ([^>]*?)src="([^"]+)"([^>]*)>', r'<img \1src="\2"\3 style="max-width:100%;height:auto;display:block;margin:22px auto;" />', raw, flags=re.S)
    raw = raw.replace("<hr />", '<hr style="border:none;border-top:1px solid #eadfcb;margin:32px 0;" />')
    return '<section style="font-size:16px;line-height:1.95;color:#222;word-break:break-word;">' + raw + "</section>"

def create_draft(tok, title, body, cover_id):
    payload = {"articles": [{"article_type": "news", "title": title, "author": AUTHOR[:16], "content": body, "content_source_url": "", "thumb_media_id": cover_id, "need_open_comment": 0, "only_fans_can_comment": 0}]}
    r = request_wechat("POST", WECHAT_API + "/draft/add", params={"access_token": tok}, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"}, timeout=90)
    d = r.json()
    if not d.get("media_id"):
        fail("创建草稿失败: " + str(d))
    return d["media_id"]

def main():
    if not ARTICLE.exists():
        fail("文章不存在: " + str(ARTICLE))
    md = strip_internal_notes(unwrap(ARTICLE.read_text(encoding="utf-8")))
    title = title_of(md)
    api_title = wechat_safe_title(title)
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()
    print("[ARTICLE]", title)
    print("[SHA256]", sha)
    print("[PROXY]", "Static proxy enabled" if PROXIES else "Direct connection")
    tok = token()
    body_md = re.sub(r"(?m)^#\s+.+?\s*$", "", md, count=1).lstrip()
    body_md, cover_id = render_and_replace(body_md, tok)
    media_id = create_draft(tok, api_title, styled_html(body_md), cover_id)
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps({"status": "success", "article_sha256": sha, "title": api_title, "draft_media_id": media_id}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[SUCCESS] 已保存到“且知”微信公众号草稿箱")
    print("[SAFE] 未调用任何正式发布接口")
    print("[DRAFT_MEDIA_ID]", media_id)

if __name__ == "__main__":
    main()
