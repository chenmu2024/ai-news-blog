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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content_os.image_resilience import prepare_images, strip_image_backup_notes

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
    if serif:
        family = "Noto Serif CJK SC:style=SemiBold" if bold else "Noto Serif CJK SC"
    else:
        family = "Noto Sans CJK SC:style=Medium" if bold else "Noto Sans CJK SC"
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

    # 大留白 + 双层细边框，避免“PPT感”
    d.rounded_rectangle((24, 24, W-24, H-24), radius=34, fill=PANEL, outline=(232, 221, 201), width=2)
    d.rounded_rectangle((42, 42, W-42, H-42), radius=28, outline=(239, 230, 214), width=1)

    title = str(spec.get("title") or "且知")
    subtitle = str(spec.get("subtitle") or "")
    kicker = str(spec.get("kicker") or "毛选方法论")

    # 顶部品牌眉题
    pill_w = 230
    x0 = (W-pill_w)//2
    d.rounded_rectangle((x0, 68, x0+pill_w, 118), radius=25, fill=(244, 234, 216))
    center_text(d, 77, "且知 · " + kicker, F(24, bold=True), DARK_RED, W)

    # 主标题使用宋体系，控制两行以内
    title_font = F(60, bold=True, serif=True)
    lines = wrap(d, title, title_font, W-180)[:2]
    title_y = 150 if len(lines) == 2 else 185
    for i, line in enumerate(lines):
        center_text(d, title_y + i*78, line, title_font, DARK_RED, W)

    # 金色细分隔线
    d.line((430, 330, 770, 330), fill=GOLD, width=2)
    d.ellipse((415, 325, 425, 335), fill=GOLD)
    d.ellipse((775, 325, 785, 335), fill=GOLD)

    if subtitle:
        sub_font = F(28)
        for i, line in enumerate(wrap(d, subtitle, sub_font, W-220)[:2]):
            center_text(d, 360 + i*40, line, sub_font, MUTED, W)

    return img

def draw_card(spec):
    W = 1080
    title = str(spec.get("title") or "且知")
    subtitle = str(spec.get("subtitle") or "")
    items = spec.get("items") or []
    if not isinstance(items, list):
        items = []
    items = items[:6]

    row_h = 216
    H = 330 + max(1, len(items))*row_h + 86
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 外框
    d.rounded_rectangle((34, 34, W-34, H-34), radius=32, fill=(249, 245, 236), outline=(232, 220, 197), width=2)

    # 顶部小眉题
    d.text((72, 62), "且知 · 毛选方法论", font=F(21, bold=True), fill=GOLD)

    # 标题区：宋体系标题 + 灰色副标题
    d.text((72, 104), title, font=F(48, bold=True, serif=True), fill=DARK_RED)
    if subtitle:
        sy = 170
        for i, line in enumerate(wrap(d, subtitle, F(26), W-144)[:2]):
            d.text((74, sy+i*36), line, font=F(26), fill=MUTED)

    divider_y = 244
    d.line((72, divider_y, W-72, divider_y), fill=(221, 205, 177), width=2)
    d.rectangle((72, divider_y-1, 220, divider_y+1), fill=GOLD)

    y = 278
    for idx, raw in enumerate(items, start=1):
        if isinstance(raw, str):
            name, lead, detail = raw, "", ""
        else:
            name = str(raw.get("name") or f"第{idx}点")
            lead = str(raw.get("lead") or "")
            detail = str(raw.get("detail") or "")

        top = y
        bottom = y + row_h - 24

        # 卡片主体
        d.rounded_rectangle((58, top, W-58, bottom), radius=26, fill=(253, 250, 244), outline=(230, 219, 199), width=2)

        # 序号徽章，比原版更轻
        badge_fill = RED if idx % 2 else (173, 132, 65)
        d.rounded_rectangle((82, top+32, 168, top+118), radius=22, fill=badge_fill)
        num = f"{idx:02d}"
        num_font = F(30, bold=True)
        box = d.textbbox((0,0), num, font=num_font)
        d.text((125-(box[2]-box[0])/2, top+57), num, font=num_font, fill=(255,255,255))

        # 内容层级：名称 > 红色结论 > 灰色解释
        d.text((202, top+27), name, font=F(34, bold=True, serif=True), fill=TEXT)

        lead_lines = wrap(d, lead, F(26, bold=True), W-304)[:2] if lead else []
        for j, line in enumerate(lead_lines):
            d.text((202, top+78+j*35), line, font=F(26, bold=True), fill=RED)

        detail_y = top + 151 if lead_lines else top + 91
        if detail:
            for j, line in enumerate(wrap(d, detail, F(23), W-304)[:2]):
                if detail_y + j*32 < bottom - 12:
                    d.text((202, detail_y+j*32), line, font=F(23), fill=MUTED)

        y += row_h

    d.text((72, H-62), "且知｜把大历史拆成小日常，把大战略拆成小习惯", font=F(20), fill=(145, 132, 113))
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

def replace_stock_images(md, tok, staged):
    """Optional licensed lifestyle pictures are uploaded through WeChat, never hotlinked."""
    if not staged:
        return md
    image_re = re.compile(r"!\\[([^\\]]*)\\]\\((https?://[^)\\s]+)\\)")
    cache = {}

    def substitute(match):
        alt, source = match.group(1), match.group(2)
        if source not in staged:
            # Internal QIEZHI_CARD pictures are already hosted by WeChat.
            return match.group(0)
        if source not in cache:
            data, mime, ext = staged[source]
            cache[source] = upload_body(tok, data, mime, ext)
        return f"![{alt}]({cache[source]})"

    return image_re.sub(substitute, md)


def styled_html(md):
    raw = markdown.markdown(md, extensions=["extra", "fenced_code", "sane_lists"], output_format="html5")

    # 二级标题：轻卡片式章节头，保留公众号阅读的呼吸感
    raw = re.sub(
        r"<h2>(.*?)</h2>",
        r'<section style="margin:38px 0 18px;padding:0 0 0 13px;border-left:4px solid #8f2219;"><h2 style="margin:0;font-family:Songti SC,STSong,Noto Serif SC,SimSun,serif;font-size:20px;line-height:1.55;font-weight:700;letter-spacing:.3px;color:#6f1812;">\1</h2></section>',
        raw, flags=re.S,
    )

    raw = re.sub(
        r"<h3>(.*?)</h3>",
        r'<h3 style="margin:30px 0 14px;font-family:Songti SC,STSong,Noto Serif SC,SimSun,serif;font-size:18px;line-height:1.65;font-weight:700;color:#2b2926;">\1</h3>',
        raw, flags=re.S,
    )

    # 正文：优先调用微信/手机系统自带中文字体
    raw = re.sub(
        r"<p>(.*?)</p>",
        r'<p style="margin:17px 0;font-family:-apple-system,BlinkMacSystemFont,PingFang SC,Hiragino Sans GB,Microsoft YaHei,Noto Sans CJK SC,Arial,sans-serif;font-size:16px;line-height:1.95;letter-spacing:.35px;text-align:justify;color:#2b2926;">\1</p>',
        raw, flags=re.S,
    )

    # 加粗不做纯黑，使用“且知”统一暗红
    raw = re.sub(
        r"<strong>(.*?)</strong>",
        r'<strong style="font-weight:700;color:#8f2219;">\1</strong>',
        raw, flags=re.S,
    )

    # 原文引用：米白底 + 暗红左线 + 宋体
    raw = re.sub(
        r"<blockquote>(.*?)</blockquote>",
        r'<blockquote style="margin:24px 0;padding:15px 18px 15px 20px;border-left:3px solid #9b2b22;border-radius:0 8px 8px 0;background:#faf5ea;color:#4a443d;"><section style="font-family:Songti SC,STSong,Noto Serif SC,SimSun,serif;font-size:16px;line-height:1.9;letter-spacing:.25px;">\1</section></blockquote>',
        raw, flags=re.S,
    )

    # 图片留白统一，不加厚边框
    raw = re.sub(
        r'<img ([^>]*?)src="([^"]+)"([^>]*)>',
        r'<img \1src="\2"\3 style="width:100%;max-width:100%;height:auto;display:block;margin:26px auto 28px;border-radius:8px;" />',
        raw, flags=re.S,
    )

    # 列表
    raw = re.sub(
        r"<ul>(.*?)</ul>",
        r'<ul style="margin:18px 0;padding-left:1.35em;font-family:-apple-system,BlinkMacSystemFont,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;font-size:16px;line-height:1.9;color:#2b2926;">\1</ul>',
        raw, flags=re.S,
    )
    raw = re.sub(
        r"<ol>(.*?)</ol>",
        r'<ol style="margin:18px 0;padding-left:1.45em;font-family:-apple-system,BlinkMacSystemFont,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;font-size:16px;line-height:1.9;color:#2b2926;">\1</ol>',
        raw, flags=re.S,
    )
    raw = re.sub(r"<li>(.*?)</li>", r'<li style="margin:8px 0;">\1</li>', raw, flags=re.S)

    # 分隔线改为极轻的暖灰线
    raw = raw.replace(
        "<hr />",
        '<section style="height:1px;background:#eadfcb;margin:34px 18% 32px;"></section>'
    )

    return (
        '<section style="font-family:-apple-system,BlinkMacSystemFont,PingFang SC,Hiragino Sans GB,Microsoft YaHei,Noto Sans CJK SC,Arial,sans-serif;'
        'font-size:16px;line-height:1.95;color:#2b2926;word-break:break-word;padding:2px 3px;">'
        + raw +
        "</section>"
    )

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
    raw_md = ARTICLE.read_text(encoding="utf-8")
    sha = hashlib.sha256(raw_md.encode("utf-8")).hexdigest()
    md = strip_image_backup_notes(strip_internal_notes(unwrap(raw_md)))
    title = title_of(md)
    api_title = wechat_safe_title(title)
    print("[ARTICLE]", title)
    print("[SHA256]", sha)
    print("[PROXY]", "Static proxy enabled" if PROXIES else "Direct connection")
    # Stage all free stock images before the first WeChat API call.
    # qiezhi retains original editorial cards by default.
    staged_stock = prepare_images(raw_md, profile="qiezhi")
    print("[STOCK_IMAGE_PREFLIGHT]", len(staged_stock))
    tok = token()
    body_md = re.sub(r"(?m)^#\s+.+?\s*$", "", md, count=1).lstrip()
    body_md = re.sub(r"(?m)^\\s*(?:\\*\\*)?作者[：:]\\s*且知(?:\\*\\*)?\\s*$", "", body_md, count=1).lstrip()
    body_md, cover_id = render_and_replace(body_md, tok)
    body_md = replace_stock_images(body_md, tok, staged_stock)
    media_id = create_draft(tok, api_title, styled_html(body_md), cover_id)
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps({"status": "success", "article_sha256": sha, "title": api_title, "draft_media_id": media_id}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[SUCCESS] 已保存到“且知”微信公众号草稿箱")
    print("[SAFE] 未调用任何正式发布接口")
    print("[DRAFT_MEDIA_ID]", media_id)

if __name__ == "__main__":
    main()
