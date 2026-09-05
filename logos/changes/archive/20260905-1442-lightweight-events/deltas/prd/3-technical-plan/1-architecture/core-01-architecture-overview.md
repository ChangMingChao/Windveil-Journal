# delta — core-01-architecture-overview.md（lightweight-events）

## ADDED — 5.6 轻量事件：结构上无提醒路径（lightweight-events，S09）

```text
数据形态
  独立表 lite_events：text_enc 加密、status（open/done 两态）、closed_at（done 配对）。
  不动 wishes 状态机——「增加事件类型」意味着改 state 枚举与全部状态机约束，
  侵入性大；独立表让轻事件与愿望天然隔离。

「结构上无提醒路径」的三重保证
  1. lite_events 无 next_trigger_at / trigger_kind 任何触发字段——Scheduler 的
     扫描 SQL 只查 wishes，轻事件表不在扫描集合中；
  2. reminder_outbox.wish_id 外键指向 wishes——轻事件没有可入箱的关联路径；
  3. 通知文案与周预算代码不引用轻事件——不存在「给轻事件发提醒」的代码分支。
  「不占用每周提醒额度」因此不是行为约定，而是数据结构使然。

Agent 边界
  轻事件不调用 LLM（无理解、无追问、无建议）——POST /lite-events 是纯写入。
  S02 的 near_term_todo 询问分支（EX-18.2）保持两选项不变，
  「先记一下」第三选项的联动另行提案。

前端形态
  P1 主输入下方「先记一下」展开区：一句话、无追问、随手划掉。
  不开新路由（与 S08 同理由：不抢导航注意力），不显示任何计数。
```

## MODIFIED — 四、组件职责与代码结构

```text
frontend/                      React 19 + Vite（纯静态产物）
  src/pages/                   /、/welcome、/garden、/wish/:id、/book、/book/:id、/me
  src/components/              愿望卡、状态徽标、半屏、时间线、记忆页、建议卡（S08）、
                               轻事件区（S09）
  src/theme/tokens.css         由 design-system.json 生成，禁止手改
  src/api/                     由后端 OpenAPI 生成的类型与客户端
backend/
  app/api/v1/                  路由层：仅做参数校验与调用 service
  app/services/                业务层：愿望状态机、提醒预算、记忆页组装、
                               偏好与可用时段、时机建议四层链路（S08）、
                               轻事件（S09）
  app/agent/                   LLMProvider 抽象、提示词、结构化输出模型、降级策略
  app/repositories/            数据访问，统一注入 owner_id
  app/models/                  SQLAlchemy 模型
  app/scheduler/               独立入口：扫描到期时机 → 写 outbox → 投递；
                               低频任务：提议过期扫描、偏好摘要生成（S08）。
                               轻事件不在任何扫描集合中（S09）
  migrations/                  Alembic
```

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
| S09 | 先记一下并随手划掉 | P1 | PWA、API、PG |
