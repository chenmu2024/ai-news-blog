# WeChat Draft Bridge

用途：把 `wechat/articles/today.md` 自动转换成微信公众号草稿。

安全边界：
- 只调用微信 `draft/add` 创建草稿。
- 不调用任何正式发布/群发接口。
- 正文图片会先验证为 PNG/JPEG，再上传到微信图片接口。
- 第一张合格图片同时作为草稿封面素材。

需要在仓库 Settings → Secrets and variables → Actions 中配置：
- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`

文章入口：`wechat/articles/today.md`
