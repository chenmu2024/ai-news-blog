# Content OS｜七公众号长期可靠性运行手册

> **每次新稿统一入口**：[PRODUCTION_BRIEF.md](PRODUCTION_BRIEF.md)。2026-10-14起，必须提交与最终正文绑定的编辑记录；旧固定字数和模板建议以该简报为准。

更新：2026-10-13；时区统一 Asia/Shanghai。此文是执行约束，不是完成保证。

**规则优先级**：2026-10-13起先执行 `content_os/AI_SCENE_POLICY.md` 的AI写实图、无图注与微信正文回读硬规则；其次执行本手册、每号最新STYLE/SOURCE_POLICY与事实/原典/版权要求；旧 `RESILIENCE_POLICY.md` 中“图卡/库存图备用”的说明只能作为额外素材备选，不得替代A–F每篇至少一张有真实生成记录、SHA256与微信正文回读的AI写实图。若相互冲突，以当前硬规则为准。

**写作质量最高优先级（从下一批新稿起）**：每次执行前必须完整阅读 `content_os/EDITORIAL_VOICE.md`、`content_os/humanizer/README.md`，同时读取相应账号 STYLE/SOURCE_POLICY 与近30日文章。七号必须采用不同的作者立场、具体证据锚点与叙事节奏，严禁全部套用“引子→五个一二三分论点→误区→总结”的通用模板。选题先说明读者真正困在哪里、有什么经过核实的细节、证据支持哪一个独立判断；初稿后必须做一轮**从目标读者视角的删改/重组编辑**，把空洞评价、重复“不是X而是Y”、机械总结、无来源的虚构故事删掉。作者感必须由真实细节、矛盾与判断产生，不能靠虚构采访、第一人称亲历或情绪金句制造。旧质量门禁只查最低合规，不可把 `Quality Gate PASS` 当作“读起来好”或“像真人写的”证明。**只对新稿执行；已经 confirmed 的历史微信草稿及archive不可为改文风而覆盖或再提交**。

**长周期运行口径**：北京时间07:00由唯一ChatGPT内容任务生产，11:20仍使用同一任务只补今日未完成号；两次运行都必须先按 `production_preflight.py` 与微信journal划分已完成/未完成/结果不明，依账号独立交付、不要等七篇写完才首次落库。GitHub Actions只负责核验、草稿桥及健康审计，无法自行调用ChatGPT图像生成能力。今天无archive/无强确认时不得报告成功，也不得把CI绿灯当成内容交付。

## 根因与处理层

1. **上游写稿是独立的 ChatGPT 定时任务**：07:00 生产7篇；11:20在同一任务中只补尚未确认成功且没有不明草稿尝试的账号。仓库本身**没有**无人值守的免费大模型原创写作服务；GitHub Actions只负责扫描、校验、官方微信草稿接口和健康审计。不要把“工作流成功”误解为“自动生成了7篇”。
2. **输入和发布器契约不一致**：用 `content_os/publish_readiness.py` 在落库前、Actions 进入上传阶段前校验标题、JSON图片卡、A封面与正文卡、D原典来源、G的5张不同正文穿搭图与来源清单。质量 Gate 和 Source Gate 不被契约校验替代。
3. **远程图片在浏览器正常但 GitHub Runner 下载失败**：所有图库/官方图片必须通过 `content_os/image_preflight.py` 实际 GET、类型/像素/解码检测；提前验证且不允许用无关图片凑数。B/C/G仍保持真实主体与许可，不能用随意库存图替换。预检失败时在**未出现草稿尝试记录之前**修正URL与来源；曾开始草稿调用的原稿严禁直接重传。
4. **字体安装长时间阻塞**：发布器先运行合约、Source/Quality/Visual/Image Gate和图片预检，再执行带超时上限的中文字体安装；已有字体时不更新 apt 缓存。
5. **状态文件跨日与旧 PASS**：新工作流执行 `--today-only`，禁止昨天稿件被当成今天稿件；每个 PASS Gate 执行 `gate_trace.py` 绑定 archive SHA256和路径。从 2026-10-11 起，健康检查须验原始字节哈希、标题、当日路径、today全文、所有 Gate 的 SHA 与微信草稿确认记录；之前的旧稿保持兼容。
6. **WeChat API 成功但 GitHub 状态写入失败**：所有发布器在**实际 draft/add 前**调用 `draft_journal.reserve` 将 `attempted` 持久写入 GitHub，对成功返回的 `media_id` 立即 `confirm`。两步均由私有 GITHUB_TOKEN 完成（不需要付费服务）。再次运行若已有同日日志却没有匹配成功回执，必须停止自动上传，调查是否已在微信草稿箱。不得用旧的 last-failure 覆盖新的成功回执。
7. **健康报告滞后**：每号成功同步后自动 workflow_dispatch `draft-health-audit.yml`；审计在读到最新 main 后重新生成报告而非回填旧快照。10:15/13:15独立计划审计仍保留，自动重试仅计划审计可执行，且见到同日草稿 attempt 日志就拒绝二次上传。GitHub定时任务是尽力执行，不能保证分钟级启动。

## 微信标题与归档完全一致（2026-10-11 起）

公众号发布器原来会在标题超过32个字符时自动截断，但成功回执有时写入完整H1，造成仓库验收与微信草稿真实标题不一致。从2026-10-11起，`publish_readiness.py` 要求所有七号新稿的H1最长32个Unicode字符，**写稿时直接取自然简洁、32字以内标题**，不能依赖接口截短。老稿历史归档不改动、不补发。

## 07:00 写稿前实际检查清单（写稿任务须主动执行）

- 先读当日 `content_os/daily-health/latest.json` **日期是否等于今天**，再分别读 A..G 的当日 archive、status/latest、today、Gate、Actions。已成功账号直接跳过，不增稿/不修改原归档。
- 读 `TOPIC_INTELLIGENCE.md`、当天公开扫描、`RESILIENCE_POLICY.md`、该号 STYLE/SOURCE_POLICY及近30天归档；微信热度不足记录 `insufficient_evidence`，继续用可信官方来源完成内容。
- 强制读取当天 `content_os/source-health/latest.json`、`content_os/editorial-intelligence/YYYY-MM-DD.json` 和 `content_os/reading-feedback/latest.json`。若 `content_os/feedback-learning/account_learning_latest.json` 存在，则同时读取；只有对应账号 `evidence_level` 不为 `insufficient` 且底层真实阅读量达到V5最低样本门槛时，才可作为一个辅助编辑信号。V5不得自动覆盖STYLE、事实门禁或账号定位。日期过期视为 stale；`reject_or_research_only` 不得直接作为主选题；`eligible_for_auto_selection=false` 只能当线索；阅读反馈只有真实 numeric_records 足够且对应标题特征 count>=3 才可作为辅助信号，缺失/未授权时保持 unknown，不得把 0、旧数据或“相对更好”换算成阅读量。主源在 GitHub Runner 健康检查失败时优先用同号可达备用源，并记录降级；可达性不等于事实已核验或版权可用。
- 先完整草拟正文与来源记录，审查标题重复、官方原典、日期、所有引用、图片许可和场景描述。G至少5张获得再使用许可的真人明星照片；A至少封面+正文知识卡。2026-10-13起，除G外每号每篇额外必须有至少1张真实生成并实际保存的AI原创写实风格图片（人物/自然/生活/史实意境须与内容相关）；AI场景不能替代政策数字卡、原典考据或真实商业证据，卡片也不能替代该写实图。AI_SCENE记录生成模型、生成ID、图片SHA、私有GitHub资产标识、用途与合成身份；publish_readiness/visual_gate/image_preflight须在已checkout的私有仓库核验文件SHA256、解码及微信媒体可用性，未真实生成/未上传则FAIL，不得伪造字段；D Source Gate 需可核验卷次和上下文，CText不可访问时须真实双版本文本回退，不能虚称影印通过。
- 从 2026-10-11 起，每号必须先给出 **3 个互不相同且都可用的标题候选**，最终标题必须是其中之一；保存到 `content_os/title-decisions/YYYY-MM-DD.json`，同时记录具体选择理由和依据（账号匹配、具体事件、30天去重、证据强度等）。最终 `selected_title` 必须与 archive 的 H1 完全一致，阅读量未知时 `verified_views=null`。标题决策缺失只触发编辑告警，绝不能因此对已成功草稿执行第二次 `draft/add`。
- 2026-10-14起先按 `PRODUCTION_BRIEF.md` 完成选题对照、Humanizer V4动态真人参考、两次阅读和逐号证据，在 `editorial-reviews/<profile>/YYYY-MM-DD.json` 保存记录；正文改变须重审。Humanizer每篇3–5个参考，至少2个来自私有Library中的500篇/2290段研究库，至少3个不同来源；按opening/structure/detail/stance/ending分工，5个参考至少覆盖4种角色；只学写法，不复制参考文本。改写后必须完成24字符精确重合污染扫描并PASS，再重新核事实。候选、标题记录、编辑记录一并提交到main后才能promotion，直接archive同样受门禁约束。缺记录不得上传，已confirmed不得因此重发。
- **提交新 archive 之前**，在临时文件上执行对应的结构、文风、源和图片校验。命令示例（以 C 为例）：

  `python content_os/publish_readiness.py --profile business --article /tmp/business-today.md`

  `python content_os/quality_gate.py --profile business_story --article /tmp/business-today.md`

  `python content_os/visual_gate.py --profile business_story --article /tmp/business-today.md`

  `python content_os/image_preflight.py --profile business --article /tmp/business-today.md`

  D额外执行对应 `source_gate.py`，G额外执行 `image_gate.py`；编辑重复标题用 `editorial_guard.py` 对照近30天归档。每张图片为真且许可可追溯后才能调用 `GitHub create_file`。
- 成功稿缺少后来新增的写实图要求只能记录视觉缺口，不能为补图重建微信草稿；不允许把成功文章改标题、换图或重写；修复失败只能针对确实尚未发起 draft/add 的文章。**HTTP超时不等于草稿创建失败**。
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

## V5 真实表现反馈闭环

- 不新增第二个定时任务。V5复用现有07:00/11:20内容任务和人工核实的阅读数据。
- 真实数据仍追加到 `content_os/reading-feedback/manual.jsonl`；允许 verified `views/likes/shares/comments/open_rate`，缺失保持null。
- 有新真实数据时依次运行：`article_feedback_database.py` → `title_performance_analyzer.py` → `account_learning_profile.py`。
- 少于5篇真实阅读量的账号统一视为数据不足；某标题特征少于3篇也不得形成学习结论。
- 输出的标题/角色表现都是相关性观察，不能表述为因果，也不能自动修改生产规则。
- 每周复盘最多选择一个单变量实验；其余生产条件尽量保持稳定，避免同时改标题、文风、选题和发布时间导致无法解释结果。

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


## 原创归档前一键检查（2026-10-11）

将待写入正文先保存为临时 Markdown，然后执行（示例）：

`python content_os/prearchive_validate.py --profile wechat --date 2026-10-11 --article /tmp/wechat-today.md`

该命令**不使用微信API、不改动历史归档和草稿**，会对实际的30天归档检查标题重复，对7号执行结构、质量、视觉及适用的原典/穿搭Gate，并实际下载解码每张正文图片；对明星穿搭强制来源、许可及真人图标记。只有状态为PASS，且候选已完成原始事实核验、授权记录及标题三选一账本，才可创建当日 archive。仅 `--skip-image-network` 的结果永远不代表发布就绪。GitHub Actions 会再次校验，并以正式文章 SHA 绑定 Gate 快照。不能把候选预检当作官方微信已建草稿证明。


## 七号候选稿自动安全转交（2026-10-11）

若 ChatGPT 写稿任务不能在本地运行Python预检，就先仅创建 `content_os/inbox/<profile>/YYYY-MM-DD.md`，及同路径 `YYYY-MM-DD.titles.json`。sidecar 必须包含恰好3个不同的标题 `candidates`、与正文H1一致的 `selected_title`、具体 `rationale`、`basis`、`verified_views:null`、以及 `evidence:{facts_checked:true,image_rights_checked:true,source_urls:[实际核实的HTTPS来源]}`。证据字段必须真实，不可通过捏造true或来源绕Gate。来源无凭证/图片版权不明的候选保持在inbox、不触发草稿。

`content-os-inbox-promote.yml` 只使用GitHub Actions，按A到G分别验证候选稿，执行 `prearchive_validate.py` 的事实/原典/视觉/质量/图片GET解码与30日去重，全部PASS后才创建原版不可变 archive 并以当日最新main合并标题账本；任何账号失败不影响其他账号。成功归档由原有 `*-draft.yml` 独立处理微信官方草稿，inbox流程绝不调用微信API，不写today/status。重复archive或draft-attempts直接SKIP。正式验收仍需confirmed journal+匹配SHA/path+media_id+PASS Gates。


## GitHub Token 不触发下游push的修复（2026-10-11）

GitHub Actions 使用默认 `GITHUB_TOKEN` 推送生成的 archive 时，不会再次触发普通 `push` 工作流。故在成功创建归档后，由 `content-os-inbox-promote.yml` 使用 `actions:write` 显式分发对应 `<profile>-draft.yml`，**只分发、不直接请求微信API**。分发前 `safe_dispatch.py` 必须核实：当天archive的最后变更确由本中转工作流提交；当天没有draft-attempts journal；今天没有旧成功回执；没有同日或运行中的对应draft Actions、Actions历史查询完整。任一异常或GitHub响应不明均停止分发，人工查询，不做盲目重试。七号互相独立，成功草稿永不重复。


## 2026-10-11 资治通鉴早期工作流失败的一次性恢复
- 当天原稿归档已完成，第一次 `Zizhi Tongjian WeChat Draft Bridge` 在安装依赖前执行 source_gate，出现 `ModuleNotFoundError: requests`，**微信草稿步骤当次为skipped**，且无 `draft-attempts/2026-10-11.json`。已将 `pip install -r zizhitongjian/requirements.txt` 移到原典 Gate 之前。
- 安全分发脚本只对此账号、当天、同一篇已验证 archive、**恰好一次**已完成的 workflow_dispatch 失败、对应原典 source step=FAIL 与 `Create Zizhi Tongjian WeChat draft only`=SKIPPED、预检成功、没有同日日志/回执的情形，允许一次额外分发，且在下次运行发现第二次工作流就停止。其余任何未知结果或API边界不清绝不能重试。该脚本只分发GitHub Actions，不直接访问微信。
