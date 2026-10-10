# Fashion Image & Source Policy

## 核心原则

**先找图，再写文章；但图片规则以实用为先，不做过度严格的授权门槛。**

允许灵活使用：
- Pexels / Unsplash / Pixabay 等公共素材站；
- 小红书、Instagram、Pinterest、品牌官网、明星公开社媒、新闻公开配图等公开可见图片；
- AI 生成图；
- 用户自有图或明确授权图。

核心要求只保留：
1. 图片来源尽量可追溯；
2. 不把 AI 图冒充真实明星、真实街拍或新闻现场；
3. 不靠看图猜品牌、型号、SKU、精确价格；
4. 避免明显私密、偷拍、付费墙内、来源完全不明、水印严重或有明确侵权警告的图片。

公开平台图片不要求必须先证明“明确可转载”才允许出稿。系统记录来源即可，不再把授权证明作为硬性阻断条件。

## 明星穿搭优先级和版权检查（2026-10-10）

**新默认是明星穿搭占80%，按连续7篇至少5篇执行**。发布前必须标明实名明星主体；5张以上真正对应明星公开造型的图片，图片必须来自可追溯的品牌、摄影机构、明星账号或媒体原页，不能把图库素人图当明星。

公开图片的可检索性与转发授权不是一回事。尽量选明确允许编辑使用的品牌资料照/授权图或有许可证的素材；遇到声明不得转载的图片不得直接复制。缺少满足许可、事实、稳定下载要求的照片时，应换同类明星选题或保留为待审核版本，不通过空白图/假AI写真/无关图凑齐五张。

FASHION_SOURCE对明星主题须 `topic_type: "celebrity"`，`subject`包含已核验的明星姓名，每一张照片的 `creator`、`source_page_url`、`rights` 必须准确，含本人真实照片。

## FASHION_SOURCE

每篇文章顶部保留隐藏 FASHION_SOURCE，用于内部追溯：

```html
<!-- FASHION_SOURCE
{
  "topic_type": "celebrity|korean|japanese|lookbook|model",
  "subject": "本篇人物/造型/主题",
  "images": [
    {
      "image_url": "正文实际使用的图片地址",
      "source_page_url": "原帖/素材页/来源页；AI 图可填持久化资产页",
      "source_platform": "pexels|unsplash|pixabay|xiaohongshu|instagram|pinterest|brand_site|news|ai|other",
      "creator": "作者/账号；能确认则填写",
      "rights": "licensed|public_platform|ai_generated|user_owned|unknown_public",
      "verified": true
    }
  ],
  "item_claims": [
    {
      "claim": "需要核验的品牌/单品/价格事实",
      "source_url": "事实来源页",
      "verified": true
    }
  ]
}
-->
```

## 图片数量

每篇至少 5 张，通常 5–8 张。优先使用小红书、Instagram、Pinterest、品牌官网/明星公开社媒等真实穿搭图片；Pexels、Unsplash、Pixabay 仅作补充。图片质量和相关性优先，不允许用 Logo 凑数。

## AI 图片

可用于穿搭示意、普通人复刻、单品组合、配色、比例、层次说明和封面。
不得写成“这就是某明星本人”“这就是某场活动真实现场”或把 AI 图当事实证据。

## 明星/平台公开图

可以用于文章编辑配图。优先保留原帖链接、账号名或来源页。
若图片只是公开可见但未核验授权，不需要因此阻断文章；内部 rights 可记为 `public_platform` 或 `unknown_public`。

## Item claims

如果正文写“同款 / 她穿的是 / 型号 / SKU / 精确价格”，必须有可核验来源。
无法确认时，改写为“同类版型 / 类似单品 / 这种肩线、裤型、配色值得抄”，不要猜。
