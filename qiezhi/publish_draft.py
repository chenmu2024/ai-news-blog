from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path

import markdown
import requests
from PIL import Image

APP_ID = os.environ["WECHAT_APP_ID"].strip()
APP_SECRET = os.environ["WECHAT_APP_SECRET"].strip()
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"].strip()
PROXY_URL = (os.getenv("PROXY_URL") or "").strip()
AUTHOR = (os.getenv("WECHAT_AUTHOR") or "且知").strip()
ARTICLE = Path(os.getenv("ARTICLE_PATH", "qiezhi/articles/today.md"))
STATUS_PATH = Path(os.getenv("STATUS_PATH", "qiezhi/status/latest.json"))
IMAGE_MODEL = (os.getenv("IMAGE_MODEL") or "gpt-image-2.5-flare").strip()
WECHAT_API = "https://api.weixin.qq.com/cgi-bin"
OPENAI_IMAGE_API = "https://api.openai.com/v1/images/generations"
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

IMAGE_RE = re.compile(
    r"<!--\s*QIEZHI_IMAGE\s+role=(cover|inline)\s*::\s*(.*?)\s*-->",
    re.S | re.I,
)

VISUAL_SUFFIX = """
统一视觉要求：这是微信公众号“且知”的知识型配图。米白或浅宣纸质感背景，暗红与黯金为主色，
现代国风知识卡片设计，克制、清晰、高级、留白充足。信息层级明确，适合手机竖屏阅读。
如果图片包含中文，只保留最关键的标题和3—6个短语，必须尽量准确清晰；不要堆小字。
不使用水印，不放无关Logo，不做政治宣传海报式构图，不出现人物崇拜式画面。
整体参考高质量中文知识信息图，而不是PPT模板。
""".strip()

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
    headings = (
        "数据核验说明", "图片说明", "配图说明", "发布说明",
        "编辑说明", "内部备注", "来源核验说明", "生成说明",
    )
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

def generate_ai_image(prompt, role):
    size = "1536x656" if role == "cover" else "1024x1280"
    full_prompt = prompt.strip() + "\n\n" + VISUAL_SUFFIX
    payload = {
        "model": IMAGE_MODEL,
        "prompt": full_prompt,
        "size": size,
        "quality": "high",
        "output_format": "png",
        "n": 1,
    }
    r = requests.post(
        OPENAI_IMAGE_API,
        headers={
            "Authorization": "Bearer " + OPENAI_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=240,
    )
    if r.status_code >= 400:
        raise RuntimeError("AI生图失败: " + r.text[:1000])
    d = r.json()
    data = d.get("data") or []
    if not data or not data[0].get("b64_json"):
        raise RuntimeError("AI生图未返回图片: " + str(d)[:1000])
    return base64.b64decode(data[0]["b64_json"])

def optimize_image(content):
    img = Image.open(BytesIO(content))
    img.thumbnail((1600, 1600))
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, "white")
        alpha = img.getchannel("A")
        bg.paste(img.convert("RGB"), mask=alpha)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    out = BytesIO()
    img.save(out, format="JPEG", quality=86, optimize=True)
    return out.getvalue(), "image/jpeg", ".jpg"

def upload_body(tok, content, mime, ext):
    r = request_wechat(
        "POST",
        WECHAT_API + "/media/uploadimg",
        params={"access_token": tok},
        files={"media": ("image" + ext, content, mime)},
        timeout=90,
    )
    d = r.json()
    if not d.get("url"):
        raise RuntimeError("正文图片上传失败: " + str(d))
    return d["url"]

def upload_cover(tok, content, mime, ext):
    r = request_wechat(
        "POST",
        WECHAT_API + "/material/add_material",
        params={"access_token": tok, "type": "image"},
        files={"media": ("cover" + ext, content, mime)},
        timeout=90,
    )
    d = r.json()
    if not d.get("media_id"):
        raise RuntimeError("封面上传失败: " + str(d))
    return d["media_id"]

def generate_and_replace(md, tok):
    cover_id = [None]
    generated = [0]

    def repl(m):
        role = m.group(1).lower()
        prompt = m.group(2).strip()
        if not prompt:
            raise RuntimeError("发现空的AI配图提示词")
        print(f"[AI_IMAGE] role={role} model={IMAGE_MODEL}")
        raw = generate_ai_image(prompt, role)
        content, mime, ext = optimize_image(raw)
        generated[0] += 1

        if role == "cover":
            if cover_id[0] is None:
                cover_id[0] = upload_cover(tok, content, mime, ext)
            return ""

        url = upload_body(tok, content, mime, ext)
        if cover_id[0] is None:
            cover_id[0] = upload_cover(tok, content, mime, ext)
        return f"![且知配图]({url})"

    out = IMAGE_RE.sub(repl, md)
    if generated[0] == 0:
        fail("文章没有 QIEZHI_IMAGE 标记，无法生成配图。")
    if not cover_id[0]:
        fail("没有可用封面图。")
    print("[AI_IMAGES]", generated[0])
    return out, cover_id[0]

def styled_html(md):
    raw = markdown.markdown(md, extensions=["extra", "fenced_code", "sane_lists"], output_format="html5")
    raw = re.sub(
        r"<h2>(.*?)</h2>",
        r'<h2 style="font-size:22px;line-height:1.55;margin:36px 0 16px;font-weight:700;color:#8f1d14;">\1</h2>',
        raw, flags=re.S,
    )
    raw = re.sub(
        r"<h3>(.*?)</h3>",
        r'<h3 style="font-size:18px;line-height:1.6;margin:28px 0 12px;font-weight:700;color:#222;">\1</h3>',
        raw, flags=re.S,
    )
    raw = re.sub(
        r"<p>(.*?)</p>",
        r'<p style="font-size:16px;line-height:1.95;margin:14px 0;color:#222;">\1</p>',
        raw, flags=re.S,
    )
    raw = re.sub(
        r"<blockquote>(.*?)</blockquote>",
        r'<blockquote style="margin:20px 0;padding:14px 18px;border-left:4px solid #a62117;background:#fbf7ef;color:#555;">\1</blockquote>',
        raw, flags=re.S,
    )
    raw = re.sub(
        r'<img ([^>]*?)src="([^"]+)"([^>]*)>',
        r'<img \1src="\2"\3 style="max-width:100%;height:auto;display:block;margin:22px auto;" />',
        raw, flags=re.S,
    )
    raw = raw.replace("<hr />", '<hr style="border:none;border-top:1px solid #eadfcb;margin:32px 0;" />')
    return '<section style="font-size:16px;line-height:1.95;color:#222;word-break:break-word;">' + raw + "</section>"

def create_draft(tok, title, body, cover_id):
    payload = {"articles": [{
        "article_type": "news",
        "title": title,
        "author": AUTHOR[:16],
        "content": body,
        "content_source_url": "",
        "thumb_media_id": cover_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }]}
    post_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = request_wechat(
        "POST",
        WECHAT_API + "/draft/add",
        params={"access_token": tok},
        data=post_data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=90,
    )
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
    body_md, cover_id = generate_and_replace(body_md, tok)
    media_id = create_draft(tok, api_title, styled_html(body_md), cover_id)
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps({
        "status": "success",
        "article_sha256": sha,
        "title": api_title,
        "draft_media_id": media_id,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[SUCCESS] 已保存到“且知”微信公众号草稿箱")
    print("[SAFE] 未调用任何正式发布接口")
    print("[DRAFT_MEDIA_ID]", media_id)

if __name__ == "__main__":
    main()
