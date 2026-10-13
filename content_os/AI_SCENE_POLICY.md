# 六公众号 AI 原创写实图生产契约（2026-10-13 起）

## 覆盖与例外
- **A qiezhi、B wechat、C business、D zizhitongjian、E parenting、F jingyun**：每篇至少 **1 张实际 AI 生成的写实风格图片**，建议2张不同构图，另按账号保留有用的知识卡、条件表、流程卡。**单独两张信息卡不能代替写实图。**
- **G fashion**：不适用AI写实硬门槛；坚持至少5张具有真实使用授权的真人明星照片，严禁AI伪装明星。
- 生效日从2026-10-13算起，2026-10-12及以前 **已 confirmed 的微信草稿不追改、不重传、不新建草稿**；缺图应在复盘记录，不以虚假成功回执补足。

## 六号画面差异
- A：自然写实的书桌、山路、田野、研读场景，可用虚构成年人，但不得冒充毛泽东本人、原始手稿。
- B：真实质感的独立开发者工作、办公环境与设备情景；**商业机构的数据、UI、产品实测只能使用已核实的真实素材**。AI概念图明确是示意。
- C：普通劳动者、政务办事大厅一般环境、家庭预算与城市生活；不生成带伪造公章、证明、文件或可识别个人身份的“官方截图”。
- D：自然写实历史气氛图/城墙/书房/自然景观；不标称真实赵奢、平原君、古籍影印或文物照片；历史真实性仍靠双版本原文。
- E：虚构成年人家庭/婴幼儿、普通住房、儿童照护生活场景；不暗示具体孩子已获补助、某医院享受免费分娩。
- F：虚构成年亚洲女性的自然写实生活、办公、散步、朋友会面场景；不称其为作者、真实投稿人或采访当事人。
- 不使用生成模型直接绘制政策金额、申请二维码、可执行按钮、中文长段落，数字全部以校验过的文字卡/HTML模板表现。

## 公开正文的视觉硬规则（高于旧STYLE/RESILIENCE选图建议）

- **A–F 的写实配图下方禁止任何说明文字或图注**，不得写“AI原创写实示意图”“AI配图”“此图为虚构人物”“摄影/来源说明”“不是真实肖像/历史现场”等。图片之后直接进入下一段正文或小标题。
- `AI_SCENE`、`generator`、`generation_id`、`sha256`、`rights`、`synthetic`、`scene_role`、`scene_description` 及编辑流程说明只保留在内部元数据、私有资产及验证日志中，写入微信正文前必须清理。只去除真实图注，不应删除独立的事实段落、政策规则或原典引文。
- C/E 的政策条件/金额信息卡可以**附加**，永远**不能替代**至少1张真正AI生成的主题相关写实图片。任何 Pexels/Unsplash 库存图、卡片、纯提示词、封面、未上传图片也不能作为AI原创写实图的替代品。
- **G fashion** 只使用获真实可复用许可的明星/日韩真人照片，至少5张必须嵌入微信草稿正文；不得使用AI伪装明星照片，只有许可明确要求时才按最低要求在正文署名。
- 草稿验收须具备同日 `confirmed` journal/`media_id`、文章SHA和PASS Gate绑定、微信 `draft/get` 返回的正文图像校验回执。2026-10-13起缺失任何一项都标记未完成。成功后的信息修改不得触发第二次 `draft/add`。
- 已确认草稿若因微信回读或状态同步失败而需要恢复，仅使用现有健康审计调度，以原 `media_id` 读取 `draft/get`。必须验证之前持久化的上传图片指纹；不接受凭空补造图片、回执或绕过事实/版权门禁。

## 生产次序（先生成实际文件，后写候选文章）
1. 按当天主题用真实可用的图像生成模型生成 JPEG/PNG/WebP 文件；记录**真实**`generator`、`generation_id` 和生成场景描述。不能只写一句“已生成”。
2. 用本地 Pillow/文件工具打开并校验真实图片，确认主题相关、不含乱码/假证据、无错误人物；记录**原文件字节**SHA256。图片要在**私有** GitHub 仓库存储为二进制，例如 `content_os/assets/ai-scenes/<profile>/YYYY-MM-DD/<unique>.webp`。需用 GitHub 二进制 blob/tree/commit/ref 上传；`create_file` 是 UTF-8 文本接口，不能用它直接保存二进制图片。
3. 由于仓库为**private**，这个 `raw.githubusercontent.com` URL 只是正文/发布器识别的资产标识，**不能假设匿名GET公开可用**。GitHub Actions 从本仓库checkout实际读取二进制，核验原字节SHA256/格式/解码并上传微信；微信返回的媒体URL随后验证 HTTP 可读。使用内部标识 `https://raw.githubusercontent.com/chenmu2024/ai-news-blog/main/content_os/assets/ai-scenes/<profile>/YYYY-MM-DD/<unique>.webp`，验证仓库中真实文件存在后，放进 Markdown 正文 `![写实AI原创场景示意](https://raw.../...webp)`。不得粘贴 `sandbox:`、ChatGPT私有图片链接或想象中的资产URL。
4. 每张**被正文使用**的AI图在文章保留一个隐藏的 `AI_SCENE` JSON：
   ```text
   <!-- AI_SCENE {"profile":"jingyun","article_date":"2026-10-13","image_url":"https://raw.githubusercontent.com/chenmu2024/ai-news-blog/main/content_os/assets/ai-scenes/jingyun/2026-10-13/scene.webp","sha256":"<真实原文件64位小写SHA256>","generator":"openai_image_gen","generation_id":"<真实工具生成ID>","rights":"ai_created_owned","synthetic":true,"scene_role":"illustration","scene_description":"成年亚洲女性在晨光中的普通书房整理笔记，未对应真实人物","pretends_to_be_real_person_or_record":false} -->
   ```
   `generator` 可使用 `openai_image_gen`、`local_ai_image_model`、`other_verified_ai_generator`，但**只能使用真实运行过的生成模型及其真实ID**。
5. `publish_readiness.py` 和 `visual_gate.py` 拒绝只有卡片而没有AI图或来源记录的稿；`image_preflight.py` 核对公开图片字节SHA256，并经 `image_resilience` 下载、解码及统一JPEG缓存；实际媒体上传、草稿图像数量还须由官方draft workflow确认。以上失败则本号 **不达标，停在候选/失败状态**，不得假称成功；其他号继续。
6. 已有 `attempted/confirmed/unknown` journal 不能为了补写实图再调用非幂等微信draft/add。如果用户另外授权修改现有草稿，也要先证明提供的是**原草稿原地修改**而非新建，且保留官方更新回执。

## 成本与运维
仅使用现有 ChatGPT 图片能力（实际可用时）、本地处理、GitHub 和既有微信 draft Actions；不新增付费图片 API、独立服务端或重复定时任务。GitHub Actions 不能自行调用本对话内的图像工具；必须由每日 ChatGPT 写稿流程实际生成并上传文件，**模型/图片生成不可用时不可用库存图假扮AI图片**，应诚实标注 `image_generation_unavailable`。
