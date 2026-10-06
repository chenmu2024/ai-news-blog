# 女装穿搭｜Image-first Content OS

内部目录：`fashion/`

定位：**明星穿搭 × 日韩穿搭 × 普通人复刻**

本方向仍坚持“先找图，再写文章”，但图片 Gate 已改为轻量规则：实用、相关、可追溯优先，不再把严格版权证明作为默认阻断条件。

## 可用图片

- Pexels / Unsplash / Pixabay 等公共素材站
- 小红书 / Instagram / Pinterest 等公开平台图片
- 品牌官网 / 明星公开社媒 / 新闻公开配图
- AI 生成穿搭示意图
- 用户自有或明确授权图片

通常 3–6 张，最低 2 张。不得用 Logo 凑数。

## Image Gate 只检查

1. 至少 2 张图片；
2. 正文实际引用；
3. FASHION_SOURCE 有基本来源记录；
4. AI 图不冒充真人/真实事件；
5. 精确品牌、SKU、价格等事实不能靠看图猜。

图片授权缺少明确声明时只做 warning，不再直接 FAIL。

## 核心文件

- `STYLE.md`
- `SOURCE_POLICY.md`
- `image_gate.py`
- `templates/article-template.md`
- `archive/YYYY-MM-DD.md`
- `articles/today.md`
- `status/image-gate.json`
- `status/quality-gate.json`
- `status/latest.json`
- `publish_draft.py`

## 发布顺序

图片候选 → 来源记录 → FASHION_SOURCE → 写作 → Image Gate → Quality Gate → 微信草稿 → 回读最终 HTML

GitHub Secrets：
- `FASHION_WECHAT_APP_ID`
- `FASHION_WECHAT_APP_SECRET`
- `PROXY_URL`

只创建草稿，不自动正式发布。
