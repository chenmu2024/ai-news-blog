# 生产合同：一篇六账号原创漫画的完整闭环
- 范围 A=qiezhi、B=wechat、C=business、D=zizhitongjian、E=parenting、F=jingyun；G=fashion 永不进入漫画路由。
- 选题前分别读取仓库最新 PRODUCTION_BRIEF、OPERATIONS、该号 STYLE/SOURCE_POLICY、最近30天标题与正文，以及既有草稿 journal；已确认的稿件必须跳过。
- 原创剧本应在不看旁白时也有因果推进，默认10–16格，每幅是独立镜头/动作，分组成5–9张手机竖向长图。人设三视图、关键道具、镜头连续性先锁定。可以打破建议数量，但必须提前调整门禁并留下编辑原因，不准重复画面凑格。
- 每格数据至少包含 id、shot（long/medium/close/detail/over_shoulder/wide/top_down/reverse/two_shot）、visible_action、setting、beat、strip_index。5–9张长图的 index 从0开始，每张对应1–3个格。
- 文本格式：Markdown正文包含所有漫画图；一篇恰有一个 `COMIC_PACKAGE` JSON隐藏标记；每张长图对应一个旧图像素材合约 `AI_SCENE` 记录，需有生成来源、生成ID、原字节SHA256及 `rights=ai_created_owned`；资产使用 GitHub 原 `content_os/assets/ai-scenes/<profile>/<date>/...` 标识与实际私有仓库存储。真实原图生成及中文合成仍属于上游的实际步骤，GitHub不能凭空生成。
- 图片与正文绑定：`COMIC_PACKAGE.images` 列明完整 `url/sha256`；任何正文里新换图片、改字、删改标题都必须重新进行完整预览和用户批准。批准记录保存 `approval:{status:"approved",by:"user",source:"chat",message_text:"同步草稿",approved_at:"时间",body_sha256:"..." }`；计算方法在 `content_os/comic_gate.py:binding_sha256`，哈希为移除COMIC_PACKAGE标记后的整个Markdown文章。
- 源与人审并行：原典/事实核验，Humanizer V4 3–5 真人语料参考且≥24连续字污染检查，双轮编辑阅读，逐图目视和手机预览，版权原创检查。程序中的 Boolean 仅是填写者声明，**不是程序能独立证明内容真实、用户授权或画质合格**。
- 在微信草稿之前：先在聊天展示所有画面，得到本次用户明确“同步草稿”；不得根据以前同意、计划时间或定时任务推断授权。随后候选inbox→prearchive_validate→归档→原公众号草稿接口，先查 journal 防止重复 POST。draft/get 按原 media_id 回读成功才可报告“已进草稿”，非正式发布。
- 旧写实图要求在 2026-10-13 及此前保持有效。2026-10-14 后新稿须通过 comic_gate；AI_SCENE沿用其文件校验和媒体上传通道，但图片主体变成**原创漫画长图**，不是写实照片。G 穿搭保持真实照片5张以上。
