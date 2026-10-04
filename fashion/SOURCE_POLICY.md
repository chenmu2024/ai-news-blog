# Fashion Image & Source Policy

## 核心原则

**图片没有解决，文章就不生成。**

“网上能看到”不是转载许可；“品牌官方”也不是自动转载许可。

## FASHION_SOURCE

每篇归档文章顶部必须包含：

```html
<!-- FASHION_SOURCE
{
  "topic_type": "celebrity|korean|japanese|lookbook|model",
  "subject": "本篇人物/造型/主题",
  "images": [
    {
      "image_url": "正文实际使用的图片直链",
      "source_page_url": "图片来源页",
      "rights": "cc0|public_domain|cc_by|licensed_press|brand_editorial_permission|affiliate_feed_permission|user_owned",
      "rights_evidence_url": "能够证明使用权的页面",
      "verified": true,
      "attribution_required": false,
      "attribution_text": ""
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

## Allowed rights

自动发布只允许：
- `cc0`
- `public_domain`
- `cc_by`
- `licensed_press`
- `brand_editorial_permission`
- `affiliate_feed_permission`
- `user_owned`
- `pexels_license`

`official`、`social_media`、`found_online`、`pinterest` 等不是许可类型，Image Gate 必须拒绝。

## Attribution

如果 `attribution_required=true`：
- `attribution_text` 不得为空；
- 正文必须真实出现该署名文字；
- 不能把必须的署名偷偷放在隐藏注释里。

## Celebrity images

明星社交媒体图、新闻报道配图、品牌普通网页图默认都只作为线索。

只有获得明确可用于编辑/公众号转载的权利证据，才能放入正文。

## Item claims

如果正文写“同款 / 她穿的是 / 型号 / SKU / 精确价格”，必须在 `item_claims` 里有对应已核验来源。

无法确认时，不写精确同款，改为版型和搭配逻辑分析。


## Pexels

Pexels 官方许可允许其照片免费用于个人与商业用途，且署名不是强制要求。使用时 rights 填 `pexels_license`，rights_evidence_url 固定指向 Pexels 官方 License 页面，并保留具体 photo page 作为 source_page_url。

仍需遵守 Pexels 对可识别人物、商标、背书暗示等限制；不得把照片中的人物说成本文品牌代言人、顾客或真实案例。
