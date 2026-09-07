# delta — test/android-ux-crud（Android 单机增量）

## ADDED — Android UX/CRUD 测试（android-ux-crud 增量）

### A.1 心语二分类（record → 愿望/轻事件）

| 编号 | 描述 | 前置条件 | 输入 | 预期 |
|------|------|---------|------|------|
| AND-UX-01 | 心语 record：未来愿望 → 未发生之地 | 模型返回 target=wish+title | 「我想去滑雪」 | 愿望表新增一行，state=seeded；不产生轻事件 |
| AND-UX-02 | 心语 record：当下小事 → 随手记 | 模型返回 target=lite+lite_event | 「今晚取快递」 | 轻事件表新增一行 open |
| AND-UX-03 | 心语 ask：空上下文换建议 | 无记录，模型走 ask | 「明天吃什么」 | 返回话题内常识建议，不出现「没找到记录」 |

### A.2 CRUD 与数据迁移

| 编号 | 描述 | 前置条件 | 操作 | 预期 |
|------|------|---------|------|------|
| AND-UX-04 | Room 1→2 迁移（lite_events 加 note/photos） | v1 库含数据 | 升级启动 | 数据保留，新列默认 null |
| AND-UX-05 | 轻事件编辑（文本+备注+照片 JSON） | 一条 open 轻事件 | updateLiteEvent | 文本/备注/照片更新落库 |
| AND-UX-06 | 记忆页删除 | 一条 memory | deleteMemory | 记录消失，愿望保持原状态 |
| AND-UX-07 | 愿望改标题 | 一条 seeded 愿望 | amend(title) | 标题更新，seededAt 不变 |

（回归：TimingCalculator 17 例 + 契约 4 例 + MockWebServer 3 例全通过）
