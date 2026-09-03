# delta — core-01-architecture-overview.md（preferences-availability-timing）

## MODIFIED — 5.1 LLM 供应商抽象与降级（对应 S01/S02/S06 的降级验收条件）

### 5.1 LLM 供应商抽象与降级（对应 S01/S02/S06 的降级验收条件）

```text
LLMProvider（抽象）
  understand_wish(text) -> WishUnderstanding | None
  ask_one_question(understanding) -> str | None
  next_smallest_step(wish, rejected: list[str]) -> str | None
  draft_memory(wish, timeline) -> MemoryDraft | None
  propose_timing(wish, context) -> TimingProposalDraft | None        # S08 增补
  summarize_preferences(preferences) -> str | None                   # S08 增补

OpenAICompatibleProvider（唯一实现）
  base_url / api_key / model 全部来自环境变量
  超时 5 秒（与验收条件「≤5 秒」对齐）、重试 1 次、失败返回 None
```

- **写入顺序强制**：`先落库用户原话 → 再调用 Provider → 再回填结构化结果`。前两步分属不同事务，第二步失败不回滚第一步。
- **降级表现**：`None` 即触发产品侧降级文案（标题回退原话前 20 字 / 「先替你收好了，我稍后再慢慢读它」），不向前端暴露任何错误码。
- **结构化输出**：用 `response_format={"type": "json_schema"}`（OpenAI 兼容层通用）约束 `WishUnderstanding`，服务端再用 Pydantic 二次校验；校验失败等同 `None`，绝不把半结构化结果写库。`propose_timing` 的 `TimingProposalDraft`（timing_type / timing_value / reason / confidence / evidence）遵循同一模式，且**只允许提出 6 种时机类型中的 4 种时间类（season / month_day / after_months / free_weekend）**——signal 与 none 不是「可执行的时间」，不由模型提议。
- **待补理解队列**：降级产生的记录写入 `pending_understanding` 表，由 Scheduler 低频重试，对应产品文案里的「稍后再慢慢读它」。`summarize_preferences` 的降级不做重试队列：摘要保持上一次的有效值（或缺失），下一周期自然重试，不阻塞任何用户操作。

## ADDED — 5.3 增补：偏好与可用时段的隐私分层（S08）

| 数据 | 分层 | 措施 |
|------|------|------|
| 用户主动声明的偏好（`declared`） | 用户内容 | `value_enc` 应用层 AES-256-GCM；可查看、可硬删除 |
| 模型推断的偏好（`inferred`） | 模型产出 | 同样加密；额外要求**可撤回**——撤回置 `revoked_at` 保留审计痕迹并立即退出一切判断；也可硬删除 |
| 偏好摘要（`kind='digest'` 行） | 模型产出 | 定期由 Scheduler 低频生成，同表存储、同样加密；可查看、可删除；生成时**只注入偏好明细与相关片段，不注入完整对话历史**（上下文有界） |
| 可用时段（`availability_windows`） | 用户内容 | 结构化字段（周几 + 分钟区间）明文存储——它们只表达「一周里什么时候可能有空」，不含内容文本；可选备注 `note_enc` 加密 |
| 时机建议（`timing_proposals`） | 模型产出 | 理由 `reason_enc` 加密；`evidence` 只存依据条目的 **ID 引用**，不复制内容——条目删除后引用自然失效，避免「删了还在用」 |

**边界重申（对应需求 5.1 的 S08 增补约束）**：模型产出的全部三类内容（推断偏好、摘要、时机建议）都只是「待用户接受的候选」，确认动作是唯一能把它们变成既有链路状态（时机字段）的通道；Scheduler 只扫描 `wishes` 的合法时机，永远不读 `timing_proposals`。

## ADDED — 5.4 TimingProposal 四层边界：模型提议、规则校验、用户确认、调度执行（S08）

```text
第 1 层 模型提议（LLM，可失败）
  输入：愿望本身 + 有界的上下文（偏好摘要、可用时段、该愿望的时间线摘要）
  输出：TimingProposalDraft（timing_type ∈ 4 种时间类 / timing_value / reason / confidence / evidence）
  落库：status='pending'，服务端立即做第 2 层校验并把结果写进 validation_result

第 2 层 规则校验（服务端，确定性）
  复用 setWishTiming 的全部校验：类型枚举、参数格式、日期存在性、时区换算
  free_weekend 额外校验：用户是否存在至少一条可用时段；无 → valid=false（PROPOSAL_NO_AVAILABILITY）
  校验失败的提议照常入库（status='expired'），validation_result 记录 reason_code——保留「为什么这条建议没成立」的审计能力
  next_trigger_at 一律由服务端计算；proposed_trigger_at 只是模型给出的参考展示值，永不写入 wishes

第 3 层 用户确认（唯一生效通道）
  confirm：服务端在事务内复用 setWishTiming 写入 wishes（等价于用户手动选择），提议转 confirmed
  reject：提议转 rejected，记录 decided_at；不写任何 wishes 字段
  过期：创建时写 expires_at（默认 7 天），Scheduler 低频扫描把超时 pending 置 expired
  结构性约束：同一愿望至多 1 条 pending（部分唯一索引）；依据条目被撤回/删除时 pending 提议立即置 expired

第 4 层 调度执行（Scheduler，与现状完全一致）
  只扫描 wishes 的 timing 字段 → reminder_outbox → 周预算与去重
  不读取 timing_proposals；提醒文案仍为模板拼接，不调用 LLM
```

为什么坚持四层而不是让模型直接算时间：需求验收条件「模型提议未经确认不会变成任何提醒」（S08）与既有设计「`next_trigger_at` 必须由服务端计算，不能由前端传入」（S03 步骤说明）是同一条原则的两个入口——模型和前端都只是「提意见的人」，时间计算与执行永远在服务端确定性代码里。

## MODIFIED — 四、组件职责与代码结构

```text
frontend/                      React 19 + Vite（纯静态产物）
  src/pages/                   /、/welcome、/garden、/wish/:id、/book、/book/:id、/me
  src/components/              愿望卡、状态徽标、半屏、时间线、记忆页、建议卡（S08）
  src/theme/tokens.css         由 design-system.json 生成，禁止手改
  src/api/                     由后端 OpenAPI 生成的类型与客户端
backend/
  app/api/v1/                  路由层：仅做参数校验与调用 service
  app/services/                业务层：愿望状态机、提醒预算、记忆页组装、
                               偏好与可用时段、时机建议四层链路（S08）
  app/agent/                   LLMProvider 抽象、提示词、结构化输出模型、降级策略
  app/repositories/            数据访问，统一注入 owner_id
  app/models/                  SQLAlchemy 模型
  app/scheduler/               独立入口：扫描到期时机 → 写 outbox → 投递；
                               低频任务：提议过期扫描、偏好摘要生成（S08）
  migrations/                  Alembic
```

## MODIFIED — 七、外部依赖与测试策略

| 依赖 | 供应商形态 | 用于场景 | 测试策略 | 说明 |
|------|-----------|---------|---------|------|
| LLM | 任意 OpenAI 兼容 `/v1/chat/completions` | S01, S02, S04, S06, S03（时机建议，S08）, S08（偏好摘要） | `mock-service` | 本地起 OpenAI 兼容 mock，返回固定结构化 JSON；另提供「强制失败」开关以覆盖全部降级验收条件。时机建议的 mock 需支持返回 `propose_timing` 固定草稿与「不可用」两种模式 |
| ASR | 任意 OpenAI 兼容 `/v1/audio/transcriptions` | S02 | `mock-service` | 同上；失败模式用于验证「保留原始音频 + 可重试转写」 |
| Web Push | 浏览器推送服务（VAPID） | S03, S04 | `env-disable` + `test-api` | 测试环境关闭真实投递，只写 `reminder_outbox`；由 `GET /api/test/outbox?user_id=` 读取以断言周预算与去重 |
| 邮件 | SMTP 或供应商 API | S03（iOS 兜底） | `test-api` | `GET /api/test/latest-email?to={email}` 返回最近一封，用于验证兜底通道与文案 |
| 对象存储 | S3 兼容 | S02, S06 | 本地 MinIO 真实调用 | 不 mock：预签名 URL 的正确性本身就是需要验证的行为 |
| 时间 | 系统时钟 | S03, S04, S06, S08（建议过期扫描） | `fixed-value` | 时机到达、60 天停滞、发生日期早于种下日期、建议 7 天过期等断言必须可注入时间，服务层统一走 `Clock` 抽象 |

## MODIFIED — 九、场景清单（作为 Phase 3 Step 1 的输入）

| 编号 | 名称 | 优先级 | 参与方 |
|------|------|--------|--------|
| S01 | 新用户建立自己的未发生之地 | P0 | PWA、API、PG、LLM |
| S02 | 随手种下一个愿望并被理解 | P0 | PWA、API、PG、对象存储、ASR、LLM |
| S03 | 为一个愿望约定属于它的时机 | P0 | PWA、API、PG、Scheduler、Push、邮件 |
| S04 | 风来了，开始第一小步 | P0 | PWA、API、PG、LLM、Scheduler |
| S05 | 回看未发生之地并重新整理（S05.1 浏览 / S05.2 整理） | P1 | PWA、API、PG |
| S06 | 把发生过的事写成一页记忆 | P0 | PWA、API、PG、对象存储、LLM |
| S07 | 唤回一个被安静放下的愿望 | P2 | PWA、API、PG |
| S08 | 管理偏好与可用时段 | P1 | PWA、API、PG、LLM、Scheduler |
