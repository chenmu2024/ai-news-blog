# Portable Humanizer V4｜七公众号强制真人化层

生效：2026-10-14 新稿。位于 Draft 与两次编辑阅读之间，不调用微信接口、不创建草稿、不自动发布。

## V4 做什么

V3 解决“要参考真人文章”。V4 进一步解决两个问题：

1. **参考选错**：不再只找最相似的几段，而是综合主题相似度、文体匹配、账号匹配、结构角色四层信号；
2. **参考污染**：Humanizer 后必须扫描最终稿是否带入所选真人参考的独特长句，连续精确重合达到24个标准化字符即退回重写。

它不是 AI 检测器，也不追求所谓“100%人类检测率”。

## 私有参考库

旧公众号全文不放进公开 GitHub。已经持久化到用户私有 Library：

- `/微信公众号/Humanizer V4/reference_article_bank_500.jsonl`
- `/微信公众号/Humanizer V4/reference_segment_bank_2290.jsonl`

基础数据：714,075篇旧公众号文章，主要为2014–2016年；精选500篇文章、2290个高质量段落、382个来源。

## 多角色检索

每篇稿件动态取3–5个参考。理想的5个角色是：

- `opening`：开头如何进入具体问题；
- `structure`：正文如何推进、避免五段式/PPT式结构；
- `detail`：怎样用动作、场景、数据或具体细节承载观点；
- `stance`：作者判断如何自然出现；
- `ending`：怎样收住，不机械总结或强行升华。

每个参考记录五项评分：`topic_similarity / style_fit / account_fit / structure_fit / total`。至少2个来自项目私有库、至少3个不同来源；5个参考时至少覆盖4种不同角色。

参考文章永远不能作为事实来源。

## 防参考污染

上游对最终稿与所选项目参考执行 `private_exact_overlap_v1`：

- 去空白和标点后做精确最长连续重合；
- 阈值24字符；
- 任一参考达到或超过24字符：FAIL，必须重写；
- 对网络标杆也必须做一次人工/模型级文本重合检查；
- 结果写入当天 editorial review 的 `humanizer.pollution_check`。

公开仓库的 `pollution_gate.py` 不保存旧文章全文，只核验该扫描真实覆盖了所有项目参考且结果PASS。

## 每篇固定流程

Research / Fact Check → Draft → V4多角色真人参考 → Humanize → 参考污染扫描 → 再核事实 → 两次编辑阅读 → Humanizer/Quality/Source/Image Gates → 用户聊天确认 → 微信草稿。

模型可以换；参考库、角色路由、污染门禁、编辑证据和事实审计保持不变。
