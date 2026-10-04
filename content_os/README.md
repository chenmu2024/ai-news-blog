# 公众号 Content OS

本目录是多个公众号方向共用的发布前质量层。选题、Research、公众号生态扫描和 Humanize 由上游内容任务执行；仓库负责在真正创建草稿前再做一次可审计的硬 Gate。

## 当前 Direction Profiles

- `ai_business`：陈慕｜AI 一人公司实战
- `qiezhi`：且知｜毛选/思想方法
- `business_story`：生意显微镜｜商业故事
- `zizhitongjian`：资治通鉴｜原典·人性·决策
- `parenting`：陈慕｜育儿与家庭教育
- `jingyun`：静筠日记｜女性生活

新增公众号方向时，应新增 Profile，而不是复制整套发布链路。

## 固定全局流程

候选池 → 微信公众号 Topic Intelligence → 撞题/去重 → Research / Fact Check（原典类先过 Source Gate） → Draft → Humanize → AI味/可读性 Gate → 配图 Gate → 草稿箱 → 数据复盘。

微信公众号文章只作为选题、标题和中文读者兴趣信号；外部事实必须回到官方/原始来源或高可信独立来源核验。

## quality_gate.py

这是启发式“文风风险”检查，不是 AI 作者身份检测器，也不用于规避检测。它检查：

- 模板化套话
- 重复句式
- 段落过度整齐
- 事实/原文信号是否过少
- 作者判断是否过弱
- 一句一段是否过度机械
- 是否混入内部生产说明
- 正文长度是否异常

分数越低越好：

- 0–30：PASS
- 31–40：WARN
- >40：FAIL

GitHub Actions 中 WARN 也会阻止发布，要求上游先完成 Humanize 再重新归档，避免“带着警告也照样发”。

## 发布边界

仓库当前各 Direction 的 publish_draft.py 仍使用微信公众号官方 API（AppID/AppSecret + 可选静态代理/IP 白名单）创建草稿。只调用草稿接口，不调用正式发布/群发接口。

“Session-first / 浏览器登录态复用”的 Easel 路线目前尚未工程化到本仓库，因此不能把它描述为已经切换完成。
