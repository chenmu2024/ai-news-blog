# Humanizer V5｜真实表现反馈学习层

V5 不替代 V4，也不改变发布审批。V4 继续负责真人参考、文风重写、污染检查与事实复核；V5 只负责把**真实发布表现**回流到下一轮编辑判断。

## 三个模块

1. `article_feedback_database.py`
   - 合并 archive、标题三选一记录、editorial review / Humanizer 角色、人工核实的阅读数据。
   - 阅读量、点赞、分享、评论、打开率缺失时保持 `null`。
   - 每个账号至少有5篇真实阅读量后，才给 `performance_level`；更少统一为 `insufficient_data`。

2. `title_performance_analyzer.py`
   - 只分析真实整数 views。
   - 账号至少5篇、某标题特征至少3篇，才允许进入学习观察。
   - 输出只是相关性，不能写成“这个标题导致阅读上涨”。

3. `account_learning_profile.py`
   - 七号分别建立学习画像。
   - 数据不足时唯一建议是继续采集，不自动改方向。
   - 数据达到最低门槛后，也只给一个单变量实验建议，不自动改STYLE或发布逻辑。

## 数据输入

继续沿用 `content_os/reading-feedback/manual.jsonl`。允许字段：

```json
{"profile":"wechat","date":"2026-10-14","title":"一家AI公司…","views":123,"likes":8,"shares":3,"comments":1,"open_rate":0.21,"source":"WeChat backend/manual verified","note":"optional"}
```

其中 `views/likes/shares/comments` 必须是真实非负整数；`open_rate` 必须是0–1之间的真实值。没有就写 `null` 或不填，绝不推算。

## 使用边界

- V5 不调用微信接口；
- 不新增定时任务；
- 不用少量数据自动换赛道；
- 不覆盖用户明确的账号定位；
- 不修改事实、来源、版权、配图或“先聊天审核后同步草稿”硬门禁；
- 学习结果属于**编辑建议**，不是预测模型或因果结论。

现有07:00/11:20任务每次读取最新版 OPERATIONS；有真实表现数据时可在写作前读取 `account_learning_latest.json`。数据不足时应明确忽略，不得硬套。
