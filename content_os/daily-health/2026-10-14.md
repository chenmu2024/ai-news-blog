# 七公众号草稿健康检查 2026-10-14

仓库一致 5/7；状态：incomplete
durable草稿确认 5/7；确认状态：incomplete
标题3选1记录 5/7；编辑告警：True

| 方向 | 仓库一致 | 草稿确认模式 | 失败环节 |
|---|---|---|---|
| qiezhi | success | confirmed_journal | 无 |
| wechat | success | confirmed_journal | 无 |
| business | success | confirmed_journal | 无 |
| zizhitongjian | incomplete | unconfirmed | archive_missing_or_unreadable, archive_title_missing, receipt_date_mismatch, gate_not_bound_to_archive:source-gate.json, gate_not_bound_to_archive:quality-gate.json, gate_not_bound_to_archive:visual-gate.json, draft_add_journal_missing_or_unconfirmed, wechat_inline_image_readback_missing_or_mismatched, editorial_review:editorial_humanizer_final_excerpt_missing, editorial_review:editorial_incomplete_fact_review, editorial_review:editorial_incomplete_reader_review, editorial_review:editorial_profile_evidence_missing:conflict_and_consequence, editorial_review:editorial_profile_evidence_missing:event_sequence, editorial_review:editorial_profile_evidence_missing:historian_comment, editorial_review:editorial_review_stale_article, editorial_review:editorial_source_evidence_invalid |
| parenting | success | confirmed_journal | 无 |
| jingyun | success | confirmed_journal | 无 |
| fashion | incomplete | unconfirmed | archive_missing_or_unreadable, archive_title_missing, receipt_date_mismatch, gate_not_bound_to_archive:image-gate.json, gate_not_bound_to_archive:quality-gate.json, gate_not_bound_to_archive:visual-gate.json, draft_add_journal_missing_or_unconfirmed, wechat_inline_image_readback_missing_or_mismatched, editorial_review:editorial_fashion_each_photo_needs_analysis, editorial_review:editorial_humanizer_final_excerpt_missing, editorial_review:editorial_incomplete_fact_review, editorial_review:editorial_incomplete_reader_review, editorial_review:editorial_review_stale_article, editorial_review:editorial_source_evidence_invalid |

注：仓库 success 不等于 durable 草稿确认；2026-10-11 起 success 必须同时满足 confirmed journal + media_id。仍非微信公众号后台视觉验收。
选题扫描数据缺失；此状态不得阻断合格文章写作。
