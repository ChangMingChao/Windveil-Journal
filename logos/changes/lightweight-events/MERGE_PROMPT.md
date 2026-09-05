# 合并指令

## 变更提案
- 提案名称：lightweight-events
- 提案目录：logos/changes/lightweight-events/

## 提案内容

# 变更提案：lightweight-events

> module: core | created: 2026-09-05

## 变更原因
来自 preferences-availability-timing 提案路线图的第 3 步：「轻量日常事件——为『晚上吃啥』类轻意图增加事件类型或轻量记录表，避免把简单意图变成有提醒压力的愿望；产品上提供『种下』与『先记一下』两种入口，底层共享存储，轻事件不占用每周提醒额度」。需求文档 5.3「不做」清单中的本条已同步标记为「后续提案」。

当前的产品缺口：用户随口说一句「今晚想吃火锅」，唯一能去的地方是愿望状态机——被 Agent 理解、被追问、可能进入提醒队列，占用每周 3 条提醒的额度。轻意图被过重地对待，与设计原则「将完成理解为经历，而不是勾选」相悖。

### 2026-09-03 技术评估对本步的原始口径
「大到出国、小到晚上吃啥：可行，但产品上要分层。出国旅行适合现在的愿望状态机；『晚上吃什么』更适合做成轻量建议或当日事项，不让它占用每周提醒额度。可以做两种入口：一个是『种下』，一个是『先记一下』，底层可以共享存储。」以及第 2 条：「如果要覆盖『晚上吃啥』这类轻事件，需要增加事件类型或轻量记录表，否则会把简单意图变成有提醒压力的愿望。」

## 收敛决策（请重点确认）
| 决策点 | 本提案 | 理由 |
|--------|--------|------|
| 数据形态 | **轻量记录表**（`lite_events`），不动愿望状态机 | 「增加事件类型」意味着改 `wishes.state` 枚举与全部状态机约束，侵入性大；独立表让轻事件在结构上不可能进入提醒队列（不接 outbox 即无提醒，比「约定不提醒」更强） |
| 入口 | P1 种下页的「先记一下」次级动作 | 与主输入「种下愿望」并存，零摩擦：一句话、无 Agent、无追问 |
| 提醒 | **完全没有提醒**（不进 outbox、不占周预算、无 Scheduler 扫描） | 「不占用每周提醒额度」的更强表述：轻事件从结构上无提醒路径 |
| Agent | **不做 LLM 理解/建议**（纯记录 + 划掉） | 「先记一下」的价值就是零摩擦；轻事件建议（如「今晚想吃火锅 → 顺便记下食材」）属后续增强 |
| S02 联动 | **裁剪为后续提案** | near_term_todo 询问式确认（EX-18.2）加第三选项「先记一下」会改变已上线的 Agent 行为与验收条件，单独论证 |

## 变更类型
需求级

新场景 S09「先记一下并随手划掉」+ 新表 + 新 API + P1 入口变更，按全链路处理（含一次加表迁移）。

## 变更范围
- 影响的需求文档：
  - `prd/1-product-requirements/core-01-requirements.md` — 新增 S09 场景（触发条件/用户价值/主路径/4 条验收条件）、5.3「不做」清单修订（轻量事件落地）、5.1 技术约束加轻事件边界、追溯表更新
- 影响的功能规格：
  - `prd/2-product-design/1-feature-specs/core-01-seeding-design.md` — P1 种下页新增「先记一下」次级入口与轻事件展示区
  - `prd/2-product-design/1-feature-specs/core-06-lite-events-design.md` — 新增：S09 交互规格（记录/列表/划掉/完成）
- 影响的信息架构：
  - `prd/2-product-design/1-feature-specs/core-00-information-architecture.md` — 场景映射加 S09、P1 页面描述更新、追溯表加行
- 影响的业务场景：
  - `S09` — 新增场景时序图（使用全局 `scenario_counter.next_id=9`）
- 影响的技术架构：
  - `prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` — 轻事件组件职责与「结构上无提醒路径」的设计说明、场景清单加 S09
- 影响的 API：
  - `api/lite-events.yaml` — 新增：POST /lite-events、GET /lite-events、POST /lite-events/{id}/done、DELETE /lite-events/{id}
- 影响的 DB 表：
  - `database/schema.sql` — 新增 `lite_events`（text_enc 加密、owner 隔离、status 约束）与索引
- 影响的测试用例：
  - `test/core-S09-test-cases.md` — 新增：字段约束 / DB 约束 / 场景用例
- 影响的编排测试：
  - `scenario/core-S09-lite-events.json` — 新增编排文件；`scenario/core-00-orchestration-index.json` — 登记 S09 并更新 coverage
- 影响的部署方案：
  - `prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` — 迁移 0009（一表）、smoke 清单加「先记一下」链路

## 明确不做（本提案边界）
- 不做轻事件的任何提醒（结构上不接 outbox；「不占额度」的更强形式）；
- 不做 Agent 理解、追问与轻事件建议；
- 不改 S02 的 near_term_todo 询问分支（第三选项「先记一下」联动另行提案）；
- 不做轻事件与愿望的互相转换（「升格为愿望」需独立设计）；
- 不做轻事件导出/统计（不制造任何计数压力）。

## 部署影响
- 是否需要部署：是
- 部署原因：新表 + 新 API + P1 前端入口
- 影响环境：本地 / 测试 / 预发 / 生产（生产部署仍需单独授权）
- 是否涉及数据迁移：是——迁移 0009 新增 `lite_events` 一张表（加表类迁移，向后兼容，无数据回填）
- 是否需要回滚预案：是——应用回滚沿用上一镜像；数据库可恢复备份或保留空表（旧代码不感知）
- 是否需要 smoke：是——新增 SMOKE-core-21（先记一下 → 划掉 → 无残留），smoke 总数 20 → 21

## UI/UX 变更声明

```yaml
ui_impact: true
design_system_mode: generated
design_system_fallback_reason: ""
pages:
  - id: lite-events-entry
    prototype: core-06-lite-events-prototype.html
    description: P1 种下页「先记一下」次级入口与轻事件列表区（记录/划掉/完成），复用既有设计令牌，不出现任何计数
```

## 变更概述
新增 `lite_events` 轻量记录表与 S09 场景：P1 种下页提供「先记一下」次级入口，一句话记录轻意图（应用层加密、owner 隔离），记录后以列表呈现，可「划掉」（done）或「收走」（dismissed/删除）。轻事件在结构上没有提醒路径：不进 outbox、不被 Scheduler 扫描、不占每周 3 条提醒额度。列表不显示任何计数、不显示时间压力；空状态只有单一输入入口。Agent 与既有愿望状态机完全不受影响。

## 后续提案路线（本提案不做）
1. **S02 联动**：near_term_todo 询问式确认加第三选项「先记一下」，让「这更像这几天要办的事」的输入自然落入轻事件。
2. **轻事件建议**：Agent 基于轻事件给出轻量建议（不催促）。
3. **升格为愿望**：用户主动把一条轻事件转成正式愿望（复用 S02 种下链路）。


## 需要合并的 Delta 文件

### 1. deltas/api/lite-events.yaml

- Delta 文件：`logos\changes\lightweight-events\deltas\api\lite-events.yaml`
- 目标目录：`logos\resources\api/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 2. deltas/database/schema.sql

- Delta 文件：`logos\changes\lightweight-events\deltas\database\schema.sql`
- 目标目录：`logos\resources\database/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 3. deltas/prd/1-product-requirements/core-01-requirements.md

- Delta 文件：`logos\changes\lightweight-events\deltas\prd\1-product-requirements\core-01-requirements.md`
- 目标目录：`logos\resources\prd\1-product-requirements/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 4. deltas/prd/2-product-design/1-feature-specs/core-00-information-architecture.md

- Delta 文件：`logos\changes\lightweight-events\deltas\prd\2-product-design\1-feature-specs\core-00-information-architecture.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 5. deltas/prd/2-product-design/1-feature-specs/core-01-seeding-design.md

- Delta 文件：`logos\changes\lightweight-events\deltas\prd\2-product-design\1-feature-specs\core-01-seeding-design.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 6. deltas/prd/2-product-design/1-feature-specs/core-06-lite-events-design.md

- Delta 文件：`logos\changes\lightweight-events\deltas\prd\2-product-design\1-feature-specs\core-06-lite-events-design.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 7. deltas/prd/2-product-design/2-page-design/core-06-lite-events-prototype.html

- Delta 文件：`logos\changes\lightweight-events\deltas\prd\2-product-design\2-page-design\core-06-lite-events-prototype.html`
- 目标目录：`logos\resources\prd\2-product-design\2-page-design/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 8. deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md

- Delta 文件：`logos\changes\lightweight-events\deltas\prd\3-technical-plan\1-architecture\core-01-architecture-overview.md`
- 目标目录：`logos\resources\prd\3-technical-plan\1-architecture/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 9. deltas/prd/3-technical-plan/2-scenario-implementation/core-00-scenario-overview.md

- Delta 文件：`logos\changes\lightweight-events\deltas\prd\3-technical-plan\2-scenario-implementation\core-00-scenario-overview.md`
- 目标目录：`logos\resources\prd\3-technical-plan\2-scenario-implementation/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 10. deltas/prd/3-technical-plan/2-scenario-implementation/core-S09-lite-events.md

- Delta 文件：`logos\changes\lightweight-events\deltas\prd\3-technical-plan\2-scenario-implementation\core-S09-lite-events.md`
- 目标目录：`logos\resources\prd\3-technical-plan\2-scenario-implementation/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 11. deltas/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md

- Delta 文件：`logos\changes\lightweight-events\deltas\prd\3-technical-plan\3-deployment\core-01-deployment-plan.md`
- 目标目录：`logos\resources\prd\3-technical-plan\3-deployment/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 12. deltas/scenario/core-00-orchestration-index.json

- Delta 文件：`logos\changes\lightweight-events\deltas\scenario\core-00-orchestration-index.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 13. deltas/scenario/core-S09-lite-events.json

- Delta 文件：`logos\changes\lightweight-events\deltas\scenario\core-S09-lite-events.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 14. deltas/test/core-S09-test-cases.md

- Delta 文件：`logos\changes\lightweight-events\deltas\test\core-S09-test-cases.md`
- 目标目录：`logos\resources\test/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 15. deltas/test/smoke/core-smoke-test-cases.md

- Delta 文件：`logos\changes\lightweight-events\deltas\test\smoke\core-smoke-test-cases.md`
- 目标目录：`logos\resources\test\smoke/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

## 执行要求

1. 逐个 Delta 文件处理，每处理完一个报告修改摘要
2. 对于 ADDED 标记：在主文档的指定位置插入新内容
3. 对于 MODIFIED 标记：替换主文档中同名章节的内容
4. 对于 REMOVED 标记：从主文档中删除对应章节
5. 保持主文档的原有格式和风格
6. 如果主文档有"最后更新"时间戳，同步更新
7. 所有变更完成后，列出修改清单
8. 所有变更合并完成后，自动执行 git commit（告知用户，无需确认）：
   git add -A && git commit -m "docs(lightweight-events): merge spec deltas"
   然后提示用户：按更新后的规格实现代码，代码完成后运行 `openlogos verify` 验收，验收通过后明确授权执行 `openlogos archive lightweight-events`。
