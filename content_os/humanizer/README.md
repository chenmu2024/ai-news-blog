# Portable Humanizer V3｜七公众号强制真人化层

生效：2026-10-14 新稿。它位于 Draft 与两次编辑阅读之间，不调用微信接口、不创建草稿、不自动发布。

## 为什么放在这里

用户对 2026-10-13 稿件的明确反馈是“AI味重、没有感觉”。解决方式不是堆禁词或追求AI检测器分数，而是让每篇稿件在事实已经确定后，参考足够多的生成式AI普及前真人中文写作，再进行一次结构级重写。

Humanizer V3 是**模型无关**的：当前正文可由 GPT-5.6 Sol 执行，以后换 Claude、Gemini、DeepSeek、Qwen 或其他模型时，本目录的参考契约、账号路由、编辑证据和事实复核保持不变。

## 参考库

项目私有研究来源已经完成：

- 原始公众号语料：714,075 篇，主要为 2014–2016 年；
- 文章级精选库：500 篇；
- 高质量段落库：2,290 条；
- 来源公众号：382 个；
- 文体覆盖：story / opinion / culture / life / explainer / other。

原语料仓库声明仅研究用途，因此**旧公众号全文不复制到本公开 GitHub 仓库**。本仓库只保存统计、路由、引用ID和从样本提炼出的写作特征。运行 Humanizer 的 ChatGPT 项目保留研究语料来源。

## 每篇新稿的固定步骤

1. 事实研究和原典/政策/产品核验先完成；参考文章不能替代事实来源。
2. 根据当前 profile 读取 `account_profiles.json`。
3. 从项目参考库动态取 3–5 个最相关样例，至少2个来自项目库、至少3个不同来源；可用1–3个已阅读全文的公开网络优秀标杆补充。
4. 只提炼：开头抓点、具体程度、段落长短、叙事推进、作者判断、结尾收束。
5. 禁止复制：人名、事实、案例、独特句子、比喻、段落。
6. Humanizer 重组正文，打破过度均匀、过度完整、五段式/PPT式结构和机械总结。
7. 再核对全部数字、人名、地点、时间、政策/作品名、直接引语与事实边界。
8. 把真实参考和真实修改写入当日 `editorial-reviews/<profile>/YYYY-MM-DD.json` 的 `humanizer` 字段。
9. `prearchive_validate.py` 运行 `humanizer_gate.py`；编辑记录和正文均合格后才可进入 archive。

## 七号路由

- qiezhi：opinion / explainer / story；原典约束优先。
- wechat：explainer / opinion / story；真实商业证据优先。
- business：explainer / life；资格、入口、步骤与限制优先。
- zizhitongjian：story / culture / opinion；史事次序与原典边界优先。
- parenting：explainer / life；家庭资格、金额、入口优先。
- jingyun：life / opinion / story；生活观察、复杂情绪、克制结尾，不虚构亲历。
- fashion：culture / explainer / life；真实图片可见细节优先，不猜品牌。

## 不是检测器

`humanizer_gate.py` 只查明显的模板风险，例如模板连接词密集、连续“不是X而是Y”、过度对称编号小标题和极端均匀段落。它不会判断作者身份，也不会为了“100%人类检测”故意制造错别字或病句。
