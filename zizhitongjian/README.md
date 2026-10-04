# 资治通鉴公众号方向

定位：读《资治通鉴》，看人性、识人、决策、组织与进退。

## 核心文件

- `SOURCE_POLICY.md`：原典来源与引用硬规则
- `STYLE.md`：账号写作规范
- `sources/README.md`：固定原典入口
- `source_gate.py`：原典来源硬 Gate
- `archive/YYYY-MM-DD.md`：每日归档
- `articles/today.md`：最近一次成功进入草稿链路的正文
- `status/source-gate.json`：原典 Gate 状态
- `status/quality-gate.json`：文风 Gate 状态
- `status/latest.json`：草稿闭环状态

## 微信草稿桥

工作流：`.github/workflows/zizhitongjian-draft.yml`

只调用微信公众号 `draft/add` 创建草稿，不正式发布。

需要 GitHub Actions Secrets：
- `TONGJIAN_WECHAT_APP_ID`
- `TONGJIAN_WECHAT_APP_SECRET`
- `PROXY_URL`（与现有公众号共用）
