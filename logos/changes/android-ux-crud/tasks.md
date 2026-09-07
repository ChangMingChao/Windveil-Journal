# 实现任务

## [delta] 规格变更
- [ ] 规划测试规格 delta：deltas/test/（心语 record 二分类 + Room 迁移）

## [code] 代码实现
- [ ] Room：LiteEventEntity 增 note/photos，DB version 1→2 迁移
- [ ] 心语：record 二分类（future→愿望 / now→轻事件）；ask 空上下文换建议 + 拓展不局限清单
- [ ] 设置页：模型保存成功提示「已保存」
- [ ] 日历：定时机弹权限请求 + 二次确认写入
- [ ] 记忆页：简化（去掉保存，只收进书里）
- [ ] CRUD：愿望改标题显性入口；随手记编辑+附件；已发生之书删除+修改
- [ ] 随手记附件：文字备注 + 最多 9 张照片（相册选）
- [ ] UT：心语二分类解析；Room 迁移
- [ ] 构建部署模拟器 E2E
