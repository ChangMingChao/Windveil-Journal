# 合并指令

## 变更提案
- 提案名称：preferences-availability-timing
- 提案目录：logos/changes/preferences-availability-timing/

## 提案内容

# 变更提案：preferences-availability-timing

> module: core | created: 2026-09-03

## 变更原因
来自产品评审对后续能力的统一判断：时机判断可以引入大模型，但必须遵循「大模型提议、规则校验、用户确认、调度器执行」的边界；同时需要为用户偏好与可用时段建立可撤回、可审计的基础数据结构。

当前系统只有固定规则计算时机，LLM 仅负责愿望理解与语义分类。若直接把外部数据或模型输出接入提醒链路，会绕过现有的确定性校验、用户确认和周预算机制。本提案先完成数据契约与持久化基础，后续再单独提案接入节假日、天气、日历等工具。

### 2026-09-03 技术评估结论（六条逐项）

| # | 候选能力 | 结论 | 与本提案的关系 |
|---|---------|------|--------------|
| 1 | 大模型做时机判断 | 可行，LLM 只产出结构化 `TimingProposal`（时机类型、日期、理由、置信度、工具依据），服务端规则引擎校验日期合法性，提醒发出仍交给调度器 | 本轮范围 |
| 2 | 持久化未发生与已发生事件 | 已基本实现：未发生对应 Wish，已发生沉淀对应 Memory | 无需改动；「晚上吃啥」类轻事件需后续增加事件类型或轻量记录表 |
| 3 | 记住或总结用户偏好 | 可行，新增偏好表区分「用户主动声明」与「模型推断」，记录来源、时间、置信度；定期生成偏好摘要，按需检索 | 本轮范围 |
| 4 | 大到出国、小到晚上吃啥 | 可行但须分层：出国走现有愿望状态机，轻事件做轻量建议/当日事项，不占每周提醒额度；「种下」与「先记一下」两种入口共享底层存储 | 后续提案 |
| 5 | 询问用户什么时候有空 | 可行，增加可用时段模型；询问要克制：仅在候选事件缺少可执行时间时问，给结构化选项 | 本轮范围 |
| 6 | 进行中用照片、视频、文字记录 | 文字/照片/语音管道已有；视频不在 MIME 白名单，需后续补大小、时长、分片续传、可选转码与存储成本控制 | 后续提案 |

现状代码依据：时机为纯规则计算（`backend/app/timing.py` 的 `plan_timing`），LLM 目前只做消息语义分类（`backend/app/steps.py` 的 `classify_message`），事件模型见 `backend/app/models.py`（`Wish` / `Memory`），媒体上传管道见 `backend/app/api.py`，MIME 白名单无视频见 `backend/app/config.py`。

## 变更类型
需求级

本轮新增偏好、可用时段与模型时机提议能力的产品边界，并影响数据模型、API 契约、场景时序、测试与部署方案，按全链路变更处理。

## 变更范围
- 影响的需求文档：
  - `prd/1-product-requirements/core-01-requirements.md` — 增加偏好、可用时段与时机提议的边界、隐私要求和验收条件；保留轻量事件与视频为后续提案
- 影响的功能规格：
  - `prd/2-product-design/1-feature-specs/core-00-information-architecture.md` — 增加偏好与可用时段入口，以及时机提议的确认态
  - `prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md` — 补充时机提议卡片、确认/拒绝/失效状态和不打扰原则
- 影响的业务场景：
  - `S03` — 时机约定增加「提议待确认」分支，确认后才能进入既有规则与调度链路
  - `S08` — 新增「管理偏好与可用时段」场景，使用全局 `scenario_counter.next_id=8`
- 影响的技术架构：
  - `prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` — 增加 `TimingProposal` 边界、规则校验与调度器职责、偏好隐私分层
  - `prd/3-technical-plan/2-scenario-implementation/core-S03-set-timing.md` — 更新时序图
  - `prd/3-technical-plan/2-scenario-implementation/core-S08-preferences-availability.md` — 新增时序图
- 影响的 API：
  - `api/wishes.yaml` — 增加 `TimingProposal` 结构和用户确认/拒绝提议的接口；确认接口只接受已校验的提议，不接受客户端直接传入触发时间
  - `api/auth.yaml` — 增加偏好与可用时段的读写/删除接口，敏感值不明文回显
- 影响的 DB 表：
  - `database/schema.sql` — 新增 `user_preferences`、`availability_windows`、`timing_proposals`，并补充 owner 隔离、加密和状态约束
- 影响的测试用例：
  - `test/core-S03-test-cases.md` — 增加时机提议校验、确认、拒绝、过期及调度隔离用例
  - `test/core-S08-test-cases.md` — 新增偏好与可用时段的 UT/ST 用例
  - `test/smoke/core-smoke-test-cases.md` — 增加最小偏好读取与可用时段保存检查
- 影响的编排测试：
  - `scenario/core-S03-timing.json` — 增加提议确认链路
  - `scenario/core-S08-preferences-availability.json` — 新增 S08 flow
  - `scenario/core-00-orchestration-index.json` — 登记 S08
- 影响的部署方案：
  - `prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` — 增加三张表的向后兼容迁移、备份和回滚说明

## 部署影响
- 是否需要部署：是
- 部署原因：新增 API、数据库表和运行时校验代码，必须部署后才能保存偏好、可用时段并展示/确认时机提议
- 影响环境：本地 / 测试 / 预发 / 生产（生产部署仍需单独授权）
- 是否涉及数据迁移：是，新增三张表，不改动既有表的必填列
- 是否需要回滚预案：是，应用回滚沿用上一镜像，数据库回滚恢复迁移前备份；新增表无既有数据依赖
- 是否需要 smoke：是

## UI/UX 变更声明

```yaml
ui_impact: true
design_system_mode: generated
design_system_fallback_reason: ""
pages:
  - id: preference-settings
    prototype: core-05-preferences-availability-prototype.html
    description: 偏好与可用时段管理页，支持查看来源、调整和删除，不显示模型未确认内容为事实
  - id: timing-proposal-review
    prototype: core-05-preferences-availability-prototype.html
    description: 时机提议确认页，展示提议日期、理由、置信度和工具依据，并提供确认/拒绝出口
```

## 变更概述
本轮建立三类数据契约。`user_preferences` 区分用户主动声明与模型推断，记录来源、置信度、创建和撤回时间；`availability_windows` 保存用户声明的重复可用时段；`timing_proposals` 保存 LLM 产生的结构化提议、规则校验结果、依据与用户决策。涉及用户内容的值、理由和摘要默认应用层加密，可查看、删除，不把完整历史无界塞入模型上下文——偏好摘要由 LLM 定期生成，仅在需要判断时机时检索相关片段，历史明细保留在库中可审计、可撤回。

`TimingProposal` 只能停留在待确认、已确认、已拒绝或已过期等明确状态。服务端负责日期、时区、类型和可用时段的确定性校验；只有用户确认且校验通过后，才写入现有愿望时机字段。Scheduler 仍只扫描现有合法时机并负责提醒、去重和每周预算。向用户询问空闲时间保持克制：仅当候选事件缺少可执行时间时才询问，且始终提供结构化选项、不做开放式追问，遵守「不做每日打扰」的产品原则。本轮不接入外部工具，不自动发送由模型决定的提醒，不实现轻量事件或视频上传。

## 后续提案路线（本轮不做）
按评估建议的落地顺序，后续每一步均先走 OpenLogos 变更提案流程、先设计后实现：
1. **本轮（数据结构先行）**：偏好、可用时段、LLM 时机提案的数据契约与持久化。
2. **工具调用与外部数据源**：接入节假日、天气、日历等，为 `TimingProposal` 提供「工具依据」字段的真实来源，服务端确定性校验保留不变。
3. **轻量事件**：为「晚上吃啥」类轻意图增加事件类型或轻量记录表，避免把简单意图变成有提醒压力的愿望；产品上提供「种下」与「先记一下」两种入口，底层共享存储，轻事件不占用每周提醒额度。
4. **视频记录**：扩展现有媒体管道的 MIME 白名单，补齐大小、时长、分片续传、可选转码与存储成本控制。


## 需要合并的 Delta 文件

### 1. deltas/api/auth.yaml

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\api\auth.yaml`
- 目标目录：`logos\resources\api/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 2. deltas/api/wishes.yaml

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\api\wishes.yaml`
- 目标目录：`logos\resources\api/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 3. deltas/database/schema.sql

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\database\schema.sql`
- 目标目录：`logos\resources\database/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 4. deltas/prd/1-product-requirements/core-01-requirements.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\prd\1-product-requirements\core-01-requirements.md`
- 目标目录：`logos\resources\prd\1-product-requirements/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 5. deltas/prd/2-product-design/1-feature-specs/core-00-information-architecture.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\prd\2-product-design\1-feature-specs\core-00-information-architecture.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 6. deltas/prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\prd\2-product-design\1-feature-specs\core-02-unhappened-place-design.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 7. deltas/prd/2-product-design/1-feature-specs/core-05-preferences-availability-design.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\prd\2-product-design\1-feature-specs\core-05-preferences-availability-design.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 8. deltas/prd/2-product-design/2-page-design/core-05-preferences-availability-prototype.html

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\prd\2-product-design\2-page-design\core-05-preferences-availability-prototype.html`
- 目标目录：`logos\resources\prd\2-product-design\2-page-design/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 9. deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\prd\3-technical-plan\1-architecture\core-01-architecture-overview.md`
- 目标目录：`logos\resources\prd\3-technical-plan\1-architecture/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 10. deltas/prd/3-technical-plan/2-scenario-implementation/core-S03-set-timing.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\prd\3-technical-plan\2-scenario-implementation\core-S03-set-timing.md`
- 目标目录：`logos\resources\prd\3-technical-plan\2-scenario-implementation/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 11. deltas/prd/3-technical-plan/2-scenario-implementation/core-S08-preferences-availability.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\prd\3-technical-plan\2-scenario-implementation\core-S08-preferences-availability.md`
- 目标目录：`logos\resources\prd\3-technical-plan\2-scenario-implementation/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 12. deltas/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\prd\3-technical-plan\3-deployment\core-01-deployment-plan.md`
- 目标目录：`logos\resources\prd\3-technical-plan\3-deployment/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 13. deltas/scenario/core-00-orchestration-index.json

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\scenario\core-00-orchestration-index.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 14. deltas/scenario/core-S03-timing.json

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\scenario\core-S03-timing.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 15. deltas/scenario/core-S08-preferences-availability.json

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\scenario\core-S08-preferences-availability.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 16. deltas/test/core-S03-test-cases.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\test\core-S03-test-cases.md`
- 目标目录：`logos\resources\test/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 17. deltas/test/core-S08-test-cases.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\test\core-S08-test-cases.md`
- 目标目录：`logos\resources\test/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 18. deltas/test/smoke/core-smoke-test-cases.md

- Delta 文件：`logos\changes\preferences-availability-timing\deltas\test\smoke\core-smoke-test-cases.md`
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
   git add -A && git commit -m "docs(preferences-availability-timing): merge spec deltas"
   然后提示用户：按更新后的规格实现代码，代码完成后运行 `openlogos verify` 验收，验收通过后明确授权执行 `openlogos archive preferences-availability-timing`。
