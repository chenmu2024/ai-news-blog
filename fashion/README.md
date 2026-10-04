# 女装穿搭｜Image-first Content OS

内部目录：`fashion/`

定位：**明星穿搭 × 日韩穿搭 × 普通人复刻**

与其他公众号不同，本方向必须先过图片权利核验，再允许写文章和创建微信草稿。

## 核心文件

- `STYLE.md`：内容定位、穿搭拆解方法与文风
- `SOURCE_POLICY.md`：图片权利、单品事实与许可规则
- `image_gate.py`：图片/许可/单品来源硬 Gate
- `templates/article-template.md`
- `archive/YYYY-MM-DD.md`
- `articles/today.md`
- `status/image-gate.json`
- `status/quality-gate.json`
- `status/latest.json`
- `publish_draft.py`

## 发布顺序

图片候选 → 权利证据 → FASHION_SOURCE → 写作 → Image Gate → Quality Gate → 微信草稿 → 回读最终 HTML

## 待配置

公众号现有正式名称和作者名仍沿用用户原账号，当前系统不擅自改品牌。

GitHub Secrets：
- `FASHION_WECHAT_APP_ID`
- `FASHION_WECHAT_APP_SECRET`
- `PROXY_URL`

只创建草稿，不自动正式发布。
