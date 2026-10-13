# 新稿编辑记录（2026-10-14起）

每号每天一个UTF-8 JSON：`<profile>/YYYY-MM-DD.json`。不写入公开正文。
这是写作任务的研究/编辑结果，不是让用户每天人工填表。不存在自动生成approve的捷径。

字段：
- `schema_version`: 1；`profile`、`date`对应候选；`decision`: 仅实际完成两次阅读后填`approve`，否则`revise`。
- `article_sha256`: 最终Markdown原始UTF-8字节SHA256（含图片/隐藏元数据）；保存LF换行后计算，不能用初稿哈希。
- `policy_sha256`: `editorial_review.policy_hash(root, profile)`的返回值，绑定当前生产简报、作者规范、反馈和本号STYLE。
- `reader`、`question`、`new_information`：具体读者、解决的问题、新发现；均为有实际内容的文字。
- `topic_key`：稳定的具体主题/角度标识，例如`beijing-childcare-eligibility-renewal`；不要每天改变编号伪装新题。
- `rejected_topics`: 至少2个对象，每个包含`question`、`reason`，必须是不同问题角度及证据理由，不能只是3个标题的改写。
- `evidence`: 非空对象列表，每个有实际读取的HTTPS `url`、来源支持的具体`claim`、最终正文逐字`article_excerpt`。
  生活观察不能冒充采访；引用事实才用来源支撑，不能为了字段强塞与内容无关的权威。
  F的普通生活观察可用`kind: observation`、`url: null`，claim解释观察范围、article_excerpt对应正文；
  一旦涉及统计/健康/法律等外部事实仍必须提供真实来源。观察记录不代表个案已获证实。
- `history`: 最近3篇归档各一个对象：`path`为仓库相对路径，`difference`描述实质新增信息；不足3篇则覆盖已有篇。
  仍需阅读近30天，代码最低核对3篇记录，不声称自动完成语义去重。
- `profile_checks`: 下列对应键的值是最终正文逐字摘句（至少8字符），必须确实证明相应内容要求，不能只抄小标题。
  A: `original_context`, `single_real_problem`；B: `paid_task`, `cost_or_tradeoff`, `evidence_scope`；
  C: `eligibility`, `official_entry`, `steps_and_limits`；D: `event_sequence`, `conflict_and_consequence`, `historian_comment`；
  E: `eligibility`, `amount_example`, `official_entry`；F: `observable_detail`, `choice_and_cost`, `ending_without_lecture`。
  G: `photo_analysis`列表，每张正文图片一个对象，含`image_url`与该图独有的`article_excerpt`，不可复用同一句凑数。
- `reader_review`和`fact_review`: 两个对象各含`finding`、`change`、`final_excerpt`、`unresolved`。
  finding是本次阅读发现，change是实际修改或核对结果，final_excerpt为最终正文摘句；不能写通用“已检查”。
  未解决问题列入unresolved，非空不得approve。两次阅读可以由同一任务依次完成，不虚称独立人类审稿。
- `humanizer`（2026-10-14起新稿必填）：对象包含：
  - `version: "v3"`、`reference_library: "wechat-humanizer-v3-2014-2016"`；
  - `reference_examples`: 3–5个对象，每个含 `origin`（`project_bank`或`web_benchmark`）、`reference_id`、`source_name`、`style`、`learned_feature`；web标杆额外保存真实HTTPS `url`。至少2个`project_bank`，至少3个不同来源；style须符合该账号Humanizer profile；
  - `anti_patterns_removed`: 至少2条本稿实际删改，不能填通用占位；
  - `final_excerpt`: Humanizer后最终正文逐字摘句；
  - `copied_reference_text: false`：没有复制参考稿原句/事实；
  - `fact_recheck: true`：Humanizer后再次核对数字、人名、地点、时间、政策/作品名、直接引语和事实边界。
  旧公众号参考全文只存在ChatGPT项目研究语料，不提交到公开仓库；编辑记录只留引用ID、来源名和提炼出的写法特征。
- `feedback_applied`: 对每项适用active反馈写`id`与`change`；记录这一篇如何回应，不需要虚构阅读表现。

执行：
`python content_os/editorial_review.py --profile wechat --date YYYY-MM-DD --article content_os/inbox/wechat/YYYY-MM-DD.md`

归档前、桥接上传前、draft/add预留前与健康审计均核对此记录。
inbox正文/标题/编辑记录分多次提交时，最后补齐的编辑记录也会触发promotion重查。
报错留在候选修订；已confirmed仍然跳过，绝不因缺新记录重建旧稿。
PASS只表示这些可审计记录与文章对应，不表示事实已被机器核实或用户已经满意。
