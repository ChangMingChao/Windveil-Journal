# delta — core-S03-test-cases.md（preferences-availability-timing）

## ADDED — 1.4 时机提议（TimingProposal）单元测试（S08 增量）

> 上游：`../prd/3-technical-plan/2-scenario-implementation/core-S03-set-timing.md` 时机提议分支（P1–P16 / EX-P.1–P.5）、`../database/schema.sql`（timing_proposals）

### 1.4.1 API 字段约束（来源：wishes.yaml → createTimingProposal / confirmTimingProposal）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S03-29 | 提议的 timing_type 只接受 4 种时间类 | `TimingProposal.timing_type.enum`、架构 5.4 | 已有 seeded 愿望 | LLM mock 返回 `when_tired` 草稿 | Pydantic 校验失败等同 None → `degraded=true`，不落库（EX-P.1） |
| UT-S03-30 | confidence 超界被拒 | `timing_proposals.confidence CHECK 0–100` | — | `confidence=101` 入库 | 违反 CHECK |
| UT-S03-31 | 提议状态只允许 4 个枚举值 | `timing_proposals.status CHECK` | — | `status='sent'` | 违反 CHECK |
| UT-S03-32 | decided_at 与状态配对 | `timing_proposals_decided_state_pairing CHECK` | — | `status='confirmed'` 且 `decided_at=NULL` | 违反 CHECK |
| UT-S03-33 | 同一愿望至多 1 条 pending | `idx_timing_proposals_single_pending` | 已有 pending 提议 | 再 INSERT 一条 pending | 唯一冲突；服务端事务内先置旧提议 expired 再插入（分支 P7） |
| UT-S03-34 | evidence 只存 ID 引用且默认 '[]' | `timing_proposals.evidence` 列约定 | — | 检查新提议行 | `evidence='[]'` 或 `[{"kind","id"}]`；不含任何内容文本 |
| UT-S03-35 | confirm 请求体必须为空 | EX-P.4 | 已有 valid pending 提议 | confirm body 携带 `next_trigger_at` | 422 `PROPOSAL_CONFIRM_BODY_FORBIDDEN` |
| UT-S03-36 | confirm 拒绝非 pending 或 invalid 提议 | EX-P.3 / EX-P.2 | 提议已 expired 或 `validation.valid=false` | confirm（空 body） | 409 `PROPOSAL_EXPIRED` / `PROPOSAL_NOT_CONFIRMABLE`；wishes 无任何变化 |
| UT-S03-37 | 校验失败的提议入库即 expired 并留审计 | 分支 P8 | LLM 返回 `month_day=2027-02-30` 草稿 | POST 生成提议 | 200；行 `status='expired'`、`validation_result={"valid":false,"reason_code":"TIMING_INVALID"}` |
| UT-S03-38 | free_weekend 提议要求有可用时段 | EX-P.2、`validation.reason_code` | 用户无任何 availability 行 | 生成 `free_weekend` 提议 | `valid=false`、`reason_code="PROPOSAL_NO_AVAILABILITY"`、status=expired |
| UT-S03-39 | expires_at 默认 7 天且扫描置 expired | 分支第 3 层、`idx_timing_proposals_expiry` | 已有 pending 提议 | 时钟推进 7 天 + 1 秒 → 触发过期扫描 | `status` 转 `expired`；confirm 返回 409 |
| UT-S03-40 | 确认后 next_trigger_at 由服务端计算 | 分支 P13、S03 Step 5 说明 | 已有 valid pending 提议 | confirm | `wishes.next_trigger_at` 为服务端按 timezone 计算值；`proposed_trigger_at` 未写入 wishes 任何列 |

## ADDED — 2.5 时机提议场景测试（S08 增量）

### 主路径与异常（编排可覆盖，LLM mock 支持 `propose_timing` 模式）

| ID | 描述 | 覆盖 | 前置条件 | 操作序列 | 预期结果 |
|----|------|------|---------|---------|---------|
| ST-S03-16 | 生成→展示→确认→衔接既有提醒链路 | 分支 P1→P15 + 主图 Step 9→18 | seeded 愿望；用户已有可用时段；LLM mock 返回 `after_months=1` 草稿；已注册 push 订阅 | 生成提议 → 断言建议卡字段 → confirm → 时钟推进 → 触发一轮调度 | confirm 200；`state=brewing`；提议 `status=confirmed`；调度后 outbox 恰好 1 条 delivered；`delivered_count=1`——建议采纳后的提醒行为与手动约定完全一致 |
| ST-S03-17 | 拒绝建议不产生任何副作用 | EX-P.3 | seeded 愿望；已有 pending 提议 | reject | 200；`status=rejected`、`decided_at` 非空；`wishes` 的 state/timing 全部不变；outbox 无新增；再次生成需用户主动触发 |
| ST-S03-18 | 依据被撤回 → 建议立即失效 | EX-P.5、S08 Step 15 | pending 提议 evidence 引用某 availability 行 | `POST /me/availability/{id}` 删除该时段 → confirm | 删除后提议 `status=expired`；confirm 409 `PROPOSAL_EXPIRED`；wishes 无变化 |
| ST-S03-19 | LLM 降级：无落库、无错误码 | EX-P.1 | LLM mock 置为不可用 | POST 生成提议 | 200 `{proposal: null, degraded: true}`；`timing_proposals` 无新行；响应不含错误码；愿望数据零变化 |
| ST-S03-20 | 新提议替代旧 pending | 分支 P7 | 已有 pending 提议 | 再次 POST 生成 | 旧提议转 `expired`，新提议 `pending`；任意时刻 pending 行数 ≤ 1（部分唯一索引兜底） |
| ST-S03-21 | 通知文案仍为模板拼接 | 分支 P15 + 主图 Step 15 说明 | ST-S03-16 完成后 | 检查 outbox 文案与 mock 调用统计 | 文案逐字含用户原话摘要；确认与调度全链路 LLM `chat_completions` 调用次数为 0（`propose_timing` 除外） |

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

## MODIFIED — 四、验收条件追溯

| AC ID | 验收条件（Phase 1 S03） | 覆盖用例 |
|-------|------------------------|---------|
| S03-AC-01 | 正常：约定季节触发并在时机到达时收到通知 | ST-S03-01, UT-S03-19, UT-S03-26 |
| S03-AC-02 | 正常：时机到达但用户选择顺延 | ST-S03-11, UT-S03-28 |
| S03-AC-03 | 异常：用户选择不必提醒 | ST-S03-04, UT-S03-21 |
| S03-AC-04 | 异常：同一时间窗口内多张卡片同时触发 | ST-S03-07, ST-S03-12, UT-S03-23 |
| S08-AC-03 | 异常（S08 增补）：模型提议未经确认不会变成任何提醒 | ST-S03-16（确认前无副作用 + 确认后走既有预算）、ST-S03-17、UT-S03-35/36/40 |
| S08-AC-04（建议部分） | 异常（S08 增补）：建议依据被撤回/删除后不再引用 | ST-S03-18、UT-S03-37/38 |
