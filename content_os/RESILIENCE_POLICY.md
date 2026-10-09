# 七公众号 Content OS｜零付费容错与备用源（2026-10-09）

适用 A qiezhi / B wechat / C business / D zizhitongjian / E parenting / F jingyun / G fashion。
目标是**最大限度减少第三方源故障**，同时严格遵守原创、来源、版权、当日归档与官方微信草稿接口的安全边界。

## 一、图片：发布前预检，不再单点依赖

B/C/D/E/F/G 发布器已调用 `content_os/image_resilience.py`，在访问任何微信草稿/媒体接口**之前**，
对正文全部 Markdown 图片执行 HTTP GET、实际解码、尺寸/内容检查与 JPEG 标准化（1200 像素、质量82），
并缓存完整字节用于本次公众号图片上传。减少“上传若干图以后才发现某图403”以及 JPEG 地址实际返回 AVIF 的失败。

- 使用真实 GET + Pillow 解码，不能只看 URL、后缀、HEAD 200 或第三方索引记录。
- HTTP 429 / 5xx / 网络超时最多短暂重试三次；HTTP 403 不绕过限制，尝试已备选素材。
- Pexels 自动优先尝试原始 URL；不能解码时尝试同一照片的 `fm=jpg` 变体；
  PNG / WebP / 可解码的 AVIF 均统一转为微信兼容 JPEG，不能解码则切换备用候选。
- 禁止任意代理抓取、绕验证码、盗链手段；不在 Repo 中提交授权不明的第三方图片镜像。
- HTTP 图源拒绝私人/内网目标、非图像 MIME、空文件、超大/过小或无法解码的内容。
- **绝不悄悄丢掉一张失败的正文图，也不把无关库存图冒充明星、真实门店或历史证物**。
  缺乏合格候选时本号暂停草稿、输出准确故障；其他6号继续。

### 每次选图的两层备用

每张关键真实照片在写稿时应确认：主图、至少1个同主题/同主体且授权允许的备选图，以及各自的真实来源页。
品牌、人物与明星必须匹配内容中描述的主体，不能泛化为随便一张人物图。
最好来自不同站点，例如官方可用图片 + Pexels/Unsplash 商用许可图片；
**不能把“可公开访问”当成“有权转载”**。在正式归档前先请求图片直链 GET 并核对许可。

对于非 fashion 的文稿，在归档 Markdown 开头用隐藏元数据（只作为示意，URL 必须换成真实核验结果）：

~~~json
<!-- IMAGE_BACKUPS
{
  "images": [
    {
      "primary": "https://images.example.org/actual-main-photo.jpg",
      "alternatives": [
        {
          "image_url": "https://images.example.net/actual-licensed-alternative.jpg",
          "source_page_url": "https://example.net/photograph-source-and-license",
          "rights": "permission",
          "verified": true,
          "subject_match": true
        }
      ]
    }
  ]
}
-->
~~~

`rights` 允许：`owned`、`permission`、`pexels_license`、
`unsplash_license`、`commons_licensed`、`cc0`、`public_domain`。
**必须确认具体图片许可与使用条件**；不得为了让程序通过就虚构 `verified`、`subject_match`。
没有上述验证记录的备用图不会被自动使用。备选图 URL 必须来自不同的可靠图源，若同站点两条链接同时403，
算一个故障域，不算有效冗余。

G fashion 使用已有的 `FASHION_SOURCE.images`：每张图片可在对应图片对象内添加同格式的
`alternatives` 数组，无需在额外注释里重复维护。必须保留**5张以上不同且可成功解码的真实穿搭正文图片**，
明星名字、人物与服装事实需要有原始页面支持；无法满足时该号 Gate 不能误报 PASS。

A qiezhi 目前使用仓库内部生成的 `QIEZHI_CARD`，不需要从随机图库找古人或原典照片；
其它账号可使用仓库内部生成的信息卡，**但不能用卡片伪装缺失的真实图片证据**，也不能绕过现有 Gate。

图片预检失败时：确认没有成功的同日草稿回执 → 检查具体 HTTP/解码故障 → 替换或补充合法备选 →
修订确实可修的同日 archive → 触发 Actions → 校验状态和 SHA。若已有成功草稿回执但 SHA
改变，停止自动重传并先调查；切勿重复调用微信 draft/add。

## 二、免费选题：独立信号、旧日参考与实时来源分开

`content_os/free_topic_scan.py` 的分层设计：

1. 免费搜狗微信公众号公开索引：允许公开搜索结果，不绕验证码。
2. Google News 对 `mp.weixin.qq.com` 的免费新闻索引：索引日期不是原文发布日期。
3. **新增：Bing News 公开 RSS（仅在前两层总样本不足5时）**：
   独立提供跨平台主题与企业/机构消息线索；**不是微信文章，也不是已验证热度**。
4. 若全天第三方源皆不可用，可将上一份报告记录为
   `prior_reference_date/prior_references`，只供标题和话题发散，不能回填当日样本和热度计数。
5. 任何新闻事实必须回到官方公告、财报、原典、权威医疗/教育指南等可信原始来源核验。
   无法核实不得写成事实。

状态约束：
- 同日 `local_date` 才是当日自动扫描；旧的 `latest.json` 永远不允许冒充今日数据。
- 有当日有效扫描但缺乏5篇微信文章或2条独立热度依据：
  `topic_gate=insufficient_evidence`，如实记录样本、来源 URL、错误与 `writing_mode=fact_verified_source_fallback`；
  写作仍必须继续，不能以“扫不到热榜”为由跳过文章。
- Bing RSS 标题或上一天报告不能自动提高 `heat_evidence_count`，不能伪造榜单、阅读数、公众号作者、日期。
- 不使用 TinyFish、付费 API、登录/验证码绕过。

GitHub Actions 免费研究窗口：06:10、06:50、07:30、07:55（Asia/Shanghai）；GitHub cron 为
**尽力执行**，不是硬实时承诺。08:20 上游任务若发现报告仍不是当天，先补扫公开来源并记来源及不足，
同时继续基于官方事实准备文章；11:20 补漏仅处理当天失败号，不重复7篇。

## 三、回执、报警与验收

- 七号独立；失败信息记录精确的 URL、HTTP 状态、站点与失败 Gate/Step，不能用“图片异常”笼统带过。
- 允许对失败号进行许可范围内的可修复改动，其他成功号不重复调用草稿 API。
- 只认可当天 `archive/YYYY-MM-DD.md`、`articles/today.md`、
  `status/latest.json` 的 SHA256、标题、日期一致，所有对应 Gate PASS 且 Actions 确认完成。
- 任何源失效都不得让旧的 `daily-health/latest.json` 被当成当天完成。
- 本系统只创建**微信公众号官方草稿**，不自动正式发布、不群发。
- 未解决的外部许可、微信后台实际视觉验收等风险须单独报告，不能用单项技术检查 PASS 代替。
