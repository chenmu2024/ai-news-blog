# Content OS｜七公众号长期可靠性运行手册

更新：2026-10-11；时区统一 Asia/Shanghai。此文是执行约束，不是完成保证。

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
- 强制读取当天 `content_os/source-health/latest.json`、`content_os/editorial-intelligence/YYYY-MM-DD.json` 和 `content_os/reading-feedback/latest.json`。日期过期视为 stale；`reject_or_research_only` 不得直接作为主选题；`eligible_for_auto_selection=false` 只能当线索；阅读反馈只有真实 numeric_records 足够且对应标题特征 count>=3 才可作为辅助信号，缺失/未授权时保持 unknown，不得把 0、旧数据或“相对更好”换算成阅读量。主源在 GitHub Runner 健康检查失败时优先用同号可达备用源，并记录降级；可达性不等于事实已核验或版权可用。
- 先完整草拟正文与来源记录，审查标题重复、官方原典、日期、所有引用、图片许可和场景描述。G至少5张真实可用的正文穿搭照片；A至少封面+正文知识卡；D Source Gate 需可核验卷次和上下文，CText不可访问时须真实双版本文本回退，不能虚称影印通过。
- 从 2026-10-11 起，每号必须先给出 **3 个互不相同且都可用的标题候选**，最终标题必须是其中之一；保存到 `content_os/title-decisions/YYYY-MM-DD.json`，同时记录具体选择理由和依据（账号匹配、具体事件、30天去重、证据强度等）。最终 `selected_title` 必须与 archive 的 H1 完全一致，阅读量未知时 `verified_views=null`。标题决策缺失只触发编辑告警，绝不能因此对已成功草稿执行第二次 `draft/add`。
- **提交新 archive 之前**，在临时文件上执行对应的结构、文风、源和图片校验。命令示例（以 C 为例）：

  `python content_os/publish_readiness.py --profile business --article /tmp/business-today.md`

  `python content_os/quality_gate.py --profile business_story --article /tmp/business-today.md`

  `python content_os/visual_gate.py --profile business_story --article /tmp/business-today.md`

  `python content_os/image_preflight.py --profile business --article /tmp/business-today.md`

  D额外执行对应 `source_gate.py`，G额外执行 `image_gate.py`；编辑重复标题用 `editorial_guard.py` 对照近30天归档。每张图片为真且许可可追溯后才能调用 `GitHub create_file`。
- 不允许把成功文章改标题、换图或重写；修复失败只能针对确实尚未发起 draft/add 的文章。**HTTP超时不等于草稿创建失败**。
- 需要人工调查时，将结论与证据追加到 `content_os/manual-review/decisions.jsonl`，并用 `python content_os/manual_review.py` 校验；模型建议不得冒充人工批准。对 source/topic/fact/image/draft/retry/metrics 任一人工放行必须记录 reviewer、decision、evidence。
- 创建归档后需查 Actions 到底运行到了哪一步。仅在正文、Gate、持久草稿日志、SHA、today和成功回执全部匹配后报“公众号草稿完成”。不自动正式发布/群发。

## 11:20 补漏

1. 七号分别检查，当日7/7即结束；没有归档才补创原创文章。
2. 对失败号先看同日 run/job/log，判断失败发生在 `draft/add` **之前还是之后**。
3. 当日 `status/draft-attempts/YYYY-MM-DD.json` 不存在且对应工作流已经结束，才能认为没有接近 WeChat draft/add；仍需确认运行日志。
4. 若尝试日志存在且 state=attempted 或 confirmed，但主状态缺失/不符：停止自动重传，查已确认媒体ID及官方微信草稿列表，恢复一致回执；绝对不能让补漏任务重复 POST 草稿。
5. 审计报告相对于 `Asia/Shanghai` 当前日期过期，则标记 stale 并用实时仓库/Actions重新核对，不得用旧报告宣告成功；若 `content_os/daily-health/latest.json` 的 `alert_required=true`，必须列出 `alert_reasons` 并进入故障处理，不得只看 `success_count`。
6. 每个账号独立；来源或微信单号故障不阻塞其他6号。

## 第二轮长期故障预防（2026-10-10）

- **图片只下载一次**：七号使用 `image_preflight.py` 在无微信凭证阶段验证所有图片并保存到同一次 Runner 的临时目录；`image_resilience.py` 上传阶段必须从校验过的缓存复用JPEG，验证文章SHA、每图哈希、JPEG格式，不再次访问不稳定图片图床；缓存损坏则停发。
- **过期内容不做耗时准备**：D《资治通鉴》的幂等检查已提前至依赖/图片/字体准备之前，七号统一遵守先 `draft_preflight.py --today-only`。
- **冲突重试**：七号正文草稿成功后的 GitHub 状态同步，在多个账号同时推送时做最多7轮仓库冲突重试；重试只写状态与结果，绝不重新调用微信 `draft/add`。
- **07:45每日离线回归**：`content-os-reliability-tests.yml` 使用 `45 23 * * *`（UTC）计划每天约07:45北京时间检查语法、配置、模拟故障和最新归档；GitHub cron可能延迟，离线绿灯不代替真实草稿成功。
- **完整的已确认草稿自恢复**：新稿 `draft_journal.py` 在 `attempted` 记录中保存经过SHA绑定的Gate快照，`confirmed` 保存微信 `media_id`。健康审计遇到成功创建但本地状态回写失败时，`reconcile_confirmed.py` 可以只凭哈希一致的归档、已确认 `media_id`、PASS Gate快照恢复 `status/latest.json`、Gate和 `today.md`；绝不再次调用微信API。无 `confirmed` 或Gate快照缺失时仍失败关闭，等待调查。
- **微信真实标题一致性**：2026-10-11起新稿H1不超过32字符，防止微信接口自动截短，造成仓库标题和实际草稿不一致。历史稿仅审计，不更改。

## 质量与可用性验收

- CI `Content OS Reliability Regression Suite` 编译七个发布器和关键脚本，解析所有工作流 YAML，运行无API回归测试，并检查最新归档的发布器输入契约。
- CI绿灯只证明静态配置和模拟场景成立；**不能代表第二天定时原创任务已按时执行**，也不能保证外部网站/API永不宕机、当日具备真实微信榜单或全部图片均拥有再版授权。
- 对真正的“连续稳定运行”，至少观察连续7个自然日：每天7个当日 archive、7条一致的成功草稿回执、同日健康报告完成、0次重复 draft/add，记录每次故障阶段与恢复时间。未达到此标准不得声称问题永不复发。


## Production handoff hardening (2026-10-11)

- **Do not stall writing on stale intelligence.** Run `python content_os/production_preflight.py` first and inspect the per-account `action`. A previous-day `daily-health/latest.json`, `source-health/latest.json`, editorial shortlist or reading feedback is a **warning/insufficient_evidence**, never a reason to return without all seven articles. Research can fall back to current official sources, with concrete independently verified facts and URLs. No fabricated metrics or reused yesterday's results.
- **Deliver independently, immediately.** For each account A→G: check today's archive and journal → source and archive dedupe → draft original copy and exactly three independently usable headlines (<33 Unicode chars) → verify source and image license/GET/decode → run publish_readiness, Quality, Visual, Image and Source gates as applicable in a temporary file → persist its headline decision → CREATE only that account's immutable `archive/YYYY-MM-DD.md` → inspect its triggered GitHub Actions; do not wait to finish all seven before submitting the first. Continue other accounts if one fails. Do not edit successful archives or call WeChat directly.
- If `production_preflight.py` returns `skip_confirmed`, do not write anything to that account, even if headline ledger is missing. `manual_review_required` means no draft retry and investigate official receipt/journal with evidence. `inspect_actions_before_dispatch` means archive already exists: do not recreate it; inspect Jobs and logs, then follow safety policy. Only `write_new_archive` permits considering a new account-specific archive, after full validation.
- The non-publishing `content-os-production-watchdog.yml` records seven-account handoff at 09:20/11:45. A red/missing handoff means incomplete production, **not** permission to re-upload. All WeChat draft API calls remain restricted to existing profile Actions. GitHub Actions checks cannot substitute for a real ChatGPT writing task.
- **Do not call the task complete from a successful scan or green CI.** Report exact daily archive count and strong confirmed journal count separately. Continue A-G independently within the task; if operating time/resources are exhausted, report each missing archive/unfinished step rather than claiming the daily job succeeded. 


## 草稿入口及归档预检修复（2026-10-11）

- 临时文件名不带日期时，`publish_readiness.py` 根据 Asia/Shanghai 今天日期执行32字限制；也可使用 `--date YYYY-MM-DD` 显式指定待发布日。不要因待审文件位于 `/tmp` 而漏检标题。
- 从2026-10-11起 `draft_preflight.py` 不接受只有 `status/latest.json` success 而没有持久 `draft-attempts` journal 的草稿成功断言。journal JSON损坏、attempted、SHA/path冲突时一律停止且不得重发；journal confirmed 与完整状态一致时幂等跳过。
- 从2026-10-11起 `draft_journal.reserve` 要求 exact archive SHA/path-bound PASS Gate 快照存在才允许进入 write-ahead reservation；不得产生无法安全恢复的无 Gate 强确认草稿。
- 注意：现有排程已经接入生产巡检，但免费 ChatGPT 定时生产仍与 GitHub 校验、草稿桥分离。CI绿色、watchdog健康或任一天旧版7/7不代表今日七篇已写成、草稿已确认。若任务写不出文章，必须真实报告具体缺口。禁止用空白/无授权图片/模板文章伪造进度。
