# delta — test/core-S03-test-cases.md（heart-voice-holiday-timing）

## ADDED — 1.7 节假日时机单元测试（heart-voice-holiday-timing 增量）

> 上游：`../api/wishes.yaml` TimingInput(holiday) 与 GET /holidays

### 1.7.1 holiday 计算与枚举端点

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S03-51 | holiday 多选取最近到来的匹配日 | heart-voice-holiday-timing | 样例数据：国庆节 2026-10-01、元旦 2027-01-01 | plan_timing(holiday, [国庆节,元旦]) | timing_value=国庆节；next_trigger_at 为服务端按 timezone 计算的 10-01 09:00；occurrence= holiday:国庆节:2026-10-01 |
| UT-S03-52 | holidays 为空或缺参 → TIMING_INVALID | heart-voice-holiday-timing | 同样例 | plan_timing(holiday) / holidays=[] | 抛 TimingError（422 TIMING_INVALID） |
| UT-S03-53 | 所选名称无匹配（缺年份）→ TIMING_INVALID | heart-voice-holiday-timing | 同样例（不含该名称） | plan_timing(holiday, [不存在的节]) | 抛 TimingError，不做任何猜测 |
| UT-S03-54 | GET /holidays 返回去重名与明细 | heart-voice-holiday-timing | 同样例 | get_holidays(year=2026) | available=true；names=[国庆节,元旦]；items 按 date 升序含 date+name；缺年份时 available=false、names/items 为空 |

实现：backend/tests/test_holiday_timing.py（已通过 5/5）
