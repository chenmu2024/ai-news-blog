# Content OS｜七公众号长期可靠性运行手册

更新：2026-10-10；时区统一 Asia/Shanghai。此文是执行约束，不是完成保证。

## 根因与处理层

1. **上游写稿是独立的 ChatGPT 定时任务**：08:20 生产7篇；11:20只补缺稿与失败稿。仓库本身**没有**无人值守的免费大模型原创写作服务；GitHub Actions只负责扫描、校验、官方微信草稿接口和健康审计。不要把“工作流成功”误解为“自动生成了7篇”。
2. **输入和发布器契约不一致**：用 `content_os/publish_readiness.py` 在落库前、Actions 进入上传阶段前校验标题、JSON图片卡、A封面与正文卡、D原典来源、G的5张不同正文穿搭图与来源清单。质量 Gate 和 Source Gate 不被契约校验替代。
3. **远程图片在浏览器正常但 GitHub Runner 下载失败**：所有图库/官方图片必须通过 `content_os/image_preflight.py` 实际 GET、类型/像素/解码检测；提前验证且不允许用无关图片凑数。B/C/G仍保持真实主体与许可，不能用随意库存图替换。预检失败时在**未出现草稿尝试记录之前**修正URL与来源；曾开始草稿调用的原稿严禁直接重传。
4. **字体安装长时间阻塞**：发布器先运行合约、Source/Quality/Visual/Image Gate和图片预检，再执行带超时上限的中文字体安装；已有字体时不更新 apt 缓存。
5. **状态文件跨日与旧 PASS**：新工作流执行 `--today-only`，禁止昨天稿件被当成今天稿件；每个 PASS Gate 执行 `gate_trace.py` 绑定 archive SHA256和路径。从 2026-10-11 起，健康检查须验原始字节哈希、标题、当日路径、today全文、所有 Gate 的 SHA 与微信草稿确认记录；之前的旧稿保持兼容。
6. **WeChat API 成功但 GitHub 状态写入失败**：所有发布器在**实际 draft/add 前**调用 `draft_journal.reserve` 将 `attempted` 持久写入 GitHub，对成功返回的 `media_id` 立即 `confirm`。两步均由私有 GITHUB_TOKEN 完成（不需要付费服务）。再次运行若已有同日日志却没有匹配成功回执，必须停止自动上传，调查是否已在微信草稿箱。不得用旧的 last-failure 覆盖新的成功回执。
7. **健康报告滞后**：每号成功同步后自动 workflow_dispatch `draft-health-audit.yml`；审计在读到最新 main 后重新生成报告而非回填旧快照。10:15/13:15独立计划审计仍保留，自动重试仅计划审计可执行，且见到同日草稿 attempt 日志就拒绝二次上传。GitHub定时任务是尽力执行，不能保证分钟级启动。

## 微信标题与归档完全一致（2026-10-11 起）

公众号发布器原来会在标题超过32个字符时自动截断，但成功回执有时写入完整H1，造成仓库验收与微信草稿真实标题不一致。从2026-10-11起，`publish_readiness.py` 要求所有七号新稿的H1最长32个Unicode字符，**写稿时直接取自然简洁、32字以内标题**，不能依赖接口截短。老稿历史归档不改动、不补发。

## 08:20 写稿前实际检查清单（写稿任务须主动执行）

- 先读当日 `content_os/daily-health/latest.json` **日期是否等于今天**，再分别读 A..G 的当日 archive、status/latest、today、Gate、Actions。已成功账号直接跳过，不增稿/不修改原归档。
- 读 `TOPIC_INTELLIGENCE.md`、当天公开扫描、`RESILIENCE_POLICY.md`、该号 STYLE/SOURCE_POLICY及近30天归档；微信热度不足记录 `insufficient_evidence`，继续用可信官方来源完成内容。
- 先完整草拟正文与来源记录，审查标题重复、官方原典、日期、所有引用、图片许可和场景描述。G至少5张真实可用的正文穿搭照片；A至少封面+正文知识卡；D Source Gate 需可核验卷次和上下文，CText不可访问时须真实双版本文本回退，不能虚称影印通过。
- **提交新 archive 之前**，在临时文件上执行对应的结构、文风、源和图片校验。命令示例（以 C 为例）：

  `python content_os/publish_readiness.py --profile business --article /tmp/business-today.md`

  `python content_os/quality_gate.py --profile business_story --article /tmp/business-today.md`

  `python content_os/visual_gate.py --profile business_story --article /tmp/business-today.md`

  `python content_os/image_preflight.py --profile business --article /tmp/business-today.md`

  D额外执行对应 `source_gate.py`，G额外执行 `image_gate.py`；编辑重复标题用 `editorial_guard.py` 对照近30天归档。每张图片为真且许可可追溯后才能调用 `GitHub create_file`。
- 不允许把成功文章改标题、换图或重写；修复失败只能针对确实尚未发起 draft/add 的文章。**HTTP超时不等于草稿创建失败**。
- 创建归档后需查 Actions 到底运行到了哪一步。仅在正文、Gate、持久草稿日志、SHA、today和成功回执全部匹配后报“公众号草稿完成”。不自动正式发布/群发。

## 11:20 补漏

1. 七号分别检查，当日7/7即结束；没有归档才补创原创文章。
2. 对失败号先看同日 run/job/log，判断失败发生在 `draft/add` **之前还是之后**。
3. 当日 `status/draft-attempts/YYYY-MM-DD.json` 不存在且对应工作流已经结束，才能认为没有接近 WeChat draft/add；仍需确认运行日志。
4. 若尝试日志存在且 state=attempted 或 confirmed，但主状态缺失/不符：停止自动重传，查已确认媒体ID及官方微信草稿列表，恢复一致回执；绝对不能让补漏任务重复 POST 草稿。
5. 审计报告相对于 `Asia/Shanghai` 当前日期过期，则标记 stale 并用实时仓库/Actions重新核对，不得用旧报告宣告成功。
6. 每个账号独立；来源或微信单号故障不阻塞其他6号。

## 质量与可用性验收

- CI `Content OS Reliability Regression Suite` 编译七个发布器和关键脚本，解析所有工作流 YAML，运行无API回归测试，并检查最新归档的发布器输入契约。
- CI绿灯只证明静态配置和模拟场景成立；**不能代表第二天定时原创任务已按时执行**，也不能保证外部网站/API永不宕机、当日具备真实微信榜单或全部图片均拥有再版授权。
- 对真正的“连续稳定运行”，至少观察连续7个自然日：每天7个当日 archive、7条一致的成功草稿回执、同日健康报告完成、0次重复 draft/add，记录每次故障阶段与恢复时间。未达到此标准不得声称问题永不复发。
