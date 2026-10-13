# 公众号 Content OS

> **每次新稿统一入口**：[PRODUCTION_BRIEF.md](PRODUCTION_BRIEF.md)。2026-10-14起，必须提交与最终正文绑定的编辑记录；旧固定字数和模板建议以该简报为准。

> **先读执行手册**：`content_os/OPERATIONS.md` 是每日07:00生产和11:20补漏的前置约束。先对每篇未提交稿运行 `publish_readiness.py`、适用 Gate 和 `image_preflight.py`，不要等 Actions 创建草稿时才发现缺卡、无效图片或数据来源问题。成功回执不可覆盖；见到 `draft-attempts/YYYY-MM-DD.json` 必须先核验，不允许重发。

本目录是多个公众号方向共用的发布前质量层。选题、Research、公众号生态扫描和 Humanize 由上游内容任务执行；仓库负责在真正创建草稿前再做一次可审计的硬 Gate。

## 当前 Direction Profiles

- `ai_business`：陈慕｜AI 一人公司实战
- `qiezhi`：且知｜毛选/思想方法
- `business_story`：职工民生｜社保医保公积金及劳动者待遇（保留兼容profile名）
- `zizhitongjian`：资治通鉴｜原典·人性·决策
- `parenting`：家庭政策｜育儿补贴、生育待遇、儿童医保与托育
- `jingyun`：静筠日记｜女性生活
- `fashion`：女装穿搭｜Image-first（明星穿搭 × 日韩穿搭 × 普通人复刻）

新增公众号方向时，应新增 Profile，而不是复制整套发布链路。

## 固定全局流程

候选池 → 微信公众号 Topic Intelligence → 撞题/去重 → Research / Fact Check（原典类先过 Source Gate） → Draft → 读者阅读删改与事实阅读 → 正文绑定编辑记录 → 启发式可读性 Gate → 配图 Gate → 草稿箱 → 数据复盘。

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

GitHub Actions 中 WARN 也会阻止发布，要求上游先完成实际删改与编辑复审 再重新归档，避免“带着警告也照样发”。

## 发布边界

仓库当前各 Direction 的 publish_draft.py 仍使用微信公众号官方 API（AppID/AppSecret + 可选静态代理/IP 白名单）创建草稿。只调用草稿接口，不调用正式发布/群发接口。

“Session-first / 浏览器登录态复用”的 Easel 路线目前尚未工程化到本仓库，因此不能把它描述为已经切换完成。


## 全局微信热门选题前置

每日选题前必须先读取并执行 `content_os/TOPIC_INTELLIGENCE.md`：先用免费公开来源扫描近期同类型微信公众号热门/高表现文章，再进行本方向选题、近30天去重和事实核验。禁止使用 TinyFish；未完成微信热门扫描不得直接进入正式选题。

## 稳定性和回执验收

- 七个方向互相独立，`cancel-in-progress=false`；每次发布前先用 `content_os/draft_preflight.py` 核对 SHA-256 成功回执，重复运行不应重复创建相同草稿。
- `content_os/daily_healthcheck.py` 扫描当天七份归档、状态、标题、SHA、today 文件及 Gate，生成 `content_os/daily-health`。10:15/13:15 北京时间 GitHub Actions 自动核查并尝试恢复已存在但未成功的归档。
- 上游 07:00 ChatGPT 写作任务仍负责研究和生成文章；GitHub 不存在免费的独立原创文章生成器。选题热度不足不得阻断写作，但不能伪报热门阅读数据。
- 只有当日7/7回执与文章完全一致才能宣称仓库侧全部成功。不会调用微信正式发布接口；微信后台视觉验收另行确认。

## 外部图片与免费扫描容错（2026-10-09）

执行 `content_os/RESILIENCE_POLICY.md`：六个外图发布器在使用微信官方媒体/草稿接口前，
调用 `image_resilience.py` 完成全部图片 GET、解码、格式标准化、同图 JPEG 变体及**经明确许可核验**
的同主题备用图；不合格图不静默替换。免费 Topic Intelligence 支持 Bing RSS → Google News 通用 RSS
的独立线索备用（不计微信热门热度），当日扫描异常也继续依靠官方资料完成原创写作。
回归测试见 `content_os/tests/test_image_resilience.py`、
`.github/workflows/content-image-resilience-tests.yml`。

### 按账号分级的免费图库配图（2026-10-09）

- **A 且知 / D 资治通鉴 / E 育儿 / F 静筠日记**：可使用 Pexels、Unsplash、Pixabay 等免费授权场景图片；备用可为另一张同主题/情绪场景照，元数据注明 `scene_match: true`，不要求照片人物、地点与文章人物/历史事件相同，但**不得暗示真实事件现场或具体个案**。
- **B AI一人公司 / C 生意显微镜 / G 女装穿搭**：保持真实产品、真实公司门店/资料、真实穿搭素材标准；备用仍需主体匹配，不能用无关图替代。
- 所有外图必须可用、授权方式适用于使用场景，并在调用公众号官方草稿接口前预检解码和转换。A 号也可在现有自制卡片之外上传图库实景照；旧成功归档不重复触发草稿。

详见 `content_os/RESILIENCE_POLICY.md` 和各账号 `STYLE.md`。
