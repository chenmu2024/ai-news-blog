# 生意显微镜｜微信公众号商业故事号

定位：看懂一家公司，也看懂一个时代的生意。

## 内容入口

- 写作规范：`business/STYLE.md`
- 每日归档：`business/archive/YYYY-MM-DD.md`
- 最新文章：`business/articles/today.md`
- 发布状态：`business/status/latest.json`

## GitHub Actions 草稿桥

工作流：`.github/workflows/business-draft.yml`

只调用微信公众号 `draft/add` 创建草稿，不调用正式发布/群发接口。

需要在仓库 Settings → Secrets and variables → Actions 配置：
- `BUSINESS_WECHAT_APP_ID`
- `BUSINESS_WECHAT_APP_SECRET`
- `PROXY_URL`（沿用现有静态代理即可）

在这两个商业号 AppID/AppSecret Secret 尚未配置前，文章仍可正常生成和归档，但不能写入这个新公众号的草稿箱。
