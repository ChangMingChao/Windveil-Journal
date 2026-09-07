# standalone Android 测试规格

> 来源：standalone-mode（TimingCalculator 移植 17 例）与 android-ux-crud（UX/CRUD 批次）
> 对齐基准：backend/tests/test_holiday_timing.py（UT-S03-55~58）

> 上游：后端 tests/test_holiday_timing.py（UT-S03-55~58）为移植验收基准

### A.1 TimingCalculator 移植（app/src/test/.../TimingCalculatorTest.kt，17 例）

| 编号 | 描述 | 对齐基准 |
|------|------|---------|
| AND-ST-01 | holiday 多选取最近匹配日、触发时刻本地 9 点 | UT-S03-55 |
| AND-ST-02 | holidays 为空 → TimingInvalid | UT-S03-56 |
| AND-ST-03 | 名称无匹配 → TimingInvalid 拒绝瞎猜 | UT-S03-57 |
| AND-ST-04 | 跨年命中次年元旦 | （移植扩展） |
| AND-ST-05 | season 已过取明年 / after_months 月底回退 / month_day 过去与非法日期 | timing.py 同语义 |
| AND-ST-06 | free_weekend 下一个非调休周末 | timing.py 同语义 |
| AND-ST-07 | 卡面文案与后端 label 同语义 | timing 服务 |

（17 例全部通过；另有契约解析 4 例 + MockWebServer 3 例回归通过）

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
