# delta — test/standalone-mode 测试规格（新增 Android 端 UT）

## ADDED — Android 单机测试（standalone-mode 增量）

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
