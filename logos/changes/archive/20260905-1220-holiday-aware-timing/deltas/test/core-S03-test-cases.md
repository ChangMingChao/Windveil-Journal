# delta — core-S03-test-cases.md（holiday-aware-timing）

## ADDED — 1.5 节假日感知单元测试（S03 增量）

> 上游：`../prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` 5.5 内置节假日数据源、`../prd/3-technical-plan/2-scenario-implementation/core-S03-set-timing.md` 分支增补（EX-P.6/P.7）

### 1.5.1 数据加载与计算

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S03-41 | 加载器按年份懒加载并缓存；schema 缺字段按空集处理 | 架构 5.5 | 样例数据目录（含合法/缺字段文件） | 分别加载 | 合法文件返回 holidays/workdays 映射；缺字段文件返回空集不抛错 |
| UT-S03-42 | 调休上班的周六不算「空闲周末」 | S03 增补验收-异常1 | 样例数据：10/10（周六）在 workdays | free_weekend 计算（时钟邻近） | 触发日跳过 10/10，落在下一个非调休周末日 |
| UT-S03-43 | 长周末后首个非调休周末命中 | S03 增补验收-正常1 | 样例数据含国庆长假 | free_weekend 计算 | 触发日为长假结束后第一个非调休周末，触发时刻沿用既有上午约定 |
| UT-S03-44 | 缺年份文件安全退化 | EX-P.6 | 无该年份文件 | free_weekend 计算 + 生成建议 | 返回空集；触发日为现状语义（下一个周末）；建议正常产出且 evidence 无 calendar 条目 |
| UT-S03-45 | season/month_day/after_months 计算不受节假日影响 | 边界确认 | 样例数据 | 分别设三种时机 | 触发日与既有公式一致，无节假日顺延 |

### 1.5.2 建议链路

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S03-46 | 提议上下文包含节假日事实 | 分支 P3 增补 | 有数据年份 + 长假邻近 | 组装有界上下文 | 上下文文本含节假日日期区间/名称与调休提示 |
| UT-S03-47 | 引用节假日的建议 evidence 含 calendar 条目 | EX-P.6 / wishes.yaml | 同上 | 生成建议 | `evidence` 含 `{"kind":"calendar","id":"holidays-{year}"}`；id 非UUID（schema 已放宽） |
| UT-S03-48 | 数据文件含 source 与 updated_at（可追溯） | 架构 5.5 schema | 样例文件 | 校验必填字段 | year/source/updated_at 齐备；缺失按空集处理（与 UT-41 同一容错） |

## ADDED — 2.6 节假日感知场景测试（S03 增量）

| ID | 描述 | 覆盖 | 前置条件 | 操作序列 | 预期结果 |
|----|------|------|---------|---------|---------|
| ST-S03-22 | 手动设置 free_weekend 命中真实休息日 | 主路径 Step 5 增补 + 验收-正常1 | 受控样例数据（含调休上班周六）；时钟邻近该周末 | `PUT /timing {type:free_weekend}` → 检查 `next_trigger_at` | 200；触发日非调休上班日、为周六/周日；确认后经 confirm 路径（建议采纳）语义一致 |
| ST-S03-23 | 建议理由引用节假日并全程无副作用 | 分支 P3/P11/P12 + 验收-正常2 | 同上；LLM mock 理由引用长假 | 生成建议 → 断言 evidence 含 calendar → confirm → 时钟推进 → 调度 | 建议卡依据含节假日条目；confirm 后 outbox 恰好 1 条 delivered；文案不受节假日影响（仍为模板拼接） |

## MODIFIED — 三、覆盖度校验

- [x] Phase 1 正常验收条件（2 条）：ST-S03-01、ST-S03-11
- [x] Phase 1 异常验收条件（2 条）：ST-S03-04、ST-S03-07
- [x] EX 异常用例（9 个）：EX-4.1→ST-04、EX-4.2→ST-05、EX-9.1→ST-06、EX-11.1→ST-03、EX-14.1→ST-07/12、EX-14.2→ST-08、EX-16.1→ST-09、EX-16.2→ST-10、EX-20.1→ST-11
- [x] API required 字段：`type`（UT-01）覆盖；组合必填（season/month_day/after_months）UT-03~07 覆盖
- [x] DB UNIQUE/CHECK 约束：`idx_reminder_outbox_once`（UT-13）、`delivered_count` CHECK（UT-14）、`status` CHECK（UT-15）、`delivered_has_channel`（UT-16）、周计数 PK（UT-17）、`endpoint` UNIQUE（UT-18）、两条 wishes CHECK（UT-11/12）全部覆盖
- [x] Phase 2 交互级验收条件（4 条）：ST-S03-01/04/07/11
- [x] S08 增量 EX 异常用例（5 个）：EX-P.1→ST-19、EX-P.2→UT-37/38、EX-P.3→ST-17、EX-P.4→UT-35、EX-P.5→ST-18
- [x] S08 增量 DB 约束：`idx_timing_proposals_single_pending`（UT-33）、`status` CHECK（UT-31）、`decided_state_pairing`（UT-32）、`confidence` CHECK（UT-30）全部覆盖
- [x] 四层边界断言：模型不落时间（UT-40）、确认不接受时间字段（UT-35）、调度器不读提议（UT-40 间接 + ST-21）
- [x] holiday-aware-timing 增量（10 个）：EX-P.6→UT-44/ST-22、EX-P.7→UT-47（边界确认）；节假日 UT-41~48 全部实现；数据文件 fixed-value 策略（架构第七节）落地为样例数据注入

## MODIFIED — 四、验收条件追溯

| AC ID | 验收条件（Phase 1 S03） | 覆盖用例 |
|-------|------------------------|---------|
| S03-AC-01 | 正常：约定季节触发并在时机到达时收到通知 | ST-S03-01, UT-S03-19, UT-S03-26 |
| S03-AC-02 | 正常：时机到达但用户选择顺延 | ST-S03-11, UT-S03-28 |
| S03-AC-03 | 异常：用户选择不必提醒 | ST-S03-04, UT-S03-21 |
| S03-AC-04 | 异常：同一时间窗口内多张卡片同时触发 | ST-S03-07, ST-S03-12, UT-S03-23 |
| S08-AC-03 | 异常（S08 增补）：模型提议未经确认不会变成任何提醒 | ST-S03-16（确认前无副作用 + 确认后走既有预算）、ST-S03-17、UT-S03-35/36/40 |
| S08-AC-04（建议部分） | 异常（S08 增补）：建议依据被撤回/删除后不再引用 | ST-S03-18、UT-S03-37/38 |
| HO-AC-01 | 正常（节假日增补）：free_weekend 命中真实的休息日 | ST-S03-22, UT-S03-42, UT-S03-43 |
| HO-AC-02 | 正常（节假日增补）：时机建议的理由可以引用节假日 | ST-S03-23, UT-S03-46/47 |
| HO-AC-03 | 异常（节假日增补）：调休上班的周末不被当作「空闲周末」 | UT-S03-42, ST-S03-22 |
| HO-AC-04 | 异常（节假日增补）：节假日数据缺失时安全退化 | UT-S03-44, UT-S03-41/48 |
