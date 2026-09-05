# 合并指令

## 变更提案
- 提案名称：holiday-aware-timing
- 提案目录：logos/changes/holiday-aware-timing/

## 提案内容

# 变更提案：holiday-aware-timing

> module: core | created: 2026-09-05

## 变更原因
来自 preferences-availability-timing 提案（已归档）路线图的第 2 步：「工具调用与外部数据源——接入节假日、天气、日历等，为 TimingProposal 提供『工具依据』字段的真实来源，服务端确定性校验保留不变」。

当前 `TimingProposal.evidence` 的依据只有偏好、可用时段与时间线三类；「空闲周末」（free_weekend）的触发日计算只看「是不是周六/周日」，不识别法定调休上班日与长周末——建议「找个空闲的周末」可能落在调休上班的周六上。

### 2026-09-03 技术评估对本步的原始口径
「用工具调用接入节假日、天气、日历等，LLM 只产出结构化 TimingProposal（时机类型、日期、理由、置信度、工具依据）；服务端仍用规则引擎校验，提醒是否发出仍交给调度器。」

## 收敛决策（请重点确认）
评估口径列了三类数据源，**本提案只落地「节假日」**，天气与个人日历裁剪为后续独立提案：

| 数据源 | 本提案 | 理由 |
|--------|--------|------|
| 法定节假日 + 调休上班日 | ✅ 落地 | 内置数据文件随镜像发布，**无需用户授权、无数据出境、无供应商依赖**；直接改善 free_weekend 计算与建议理由 |
| 天气 | ❌ 另立 | 需要供应商选型（供应商中立原则）与数据出境评估 |
| 个人日历 | ❌ 另立 | 需要 OAuth 授权与敏感数据处理，隐私边界需单独设计 |

「工具调用」的形态因此是**服务端数据检索喂给 LLM 上下文**（bounded context 增加节假日事实），不是 function calling——与 S03 分支 P3「组装有界上下文」的既有设计同构。

## 变更类型
需求级

free_weekend 的触发日计算语义变化（避开调休上班日）影响 S03 的验收条件，建议卡展示与建议理由引用节假日影响产品设计；按全链路处理。**不含**数据库迁移（数据是文件不是表）。

## 变更范围
- 影响的需求文档：
  - `prd/1-product-requirements/core-01-requirements.md` — S03 增补节假日感知的验收条件（2 正常 2 异常）、5.1 技术约束加数据源边界、「不做」清单修订（天气/位置仍不做，节假日数据落地）
- 影响的功能规格：
  - `prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md` — 建议卡的依据来源说明（节假日条目的展示文案）
- 影响的业务场景：
  - `S03` — 时机提议分支 P3 组装上下文加入节假日事实；free_weekend 触发日的节假日感知计算
- 影响的技术架构：
  - `prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` — 内置节假日数据源（文件形态、年份粒度、缺年份降级）、更新机制
- 影响的 API：
  - `api/wishes.yaml` — `TimingProposal.evidence[].kind` 枚举扩展 `calendar`
- 影响的 DB 表：
  - 无（无新表、无迁移）
- 影响的测试用例：
  - `test/core-S03-test-cases.md` — 节假日感知计算 UT（调休上班周六不命中、长周末命中、缺年份降级）与建议依据 ST
- 影响的编排测试：
  - `scenario/core-S03-timing.json` — 新增 2 个 flow（节假日建议依据、调休周末不命中）
- 影响的部署方案：
  - `prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` — 数据文件随镜像发布、年度数据更新的运维项

## 明确不做（本提案边界）
- 不改 season / month_day / after_months 的既有触发日计算——改变已上线语义是隐性破坏，节假日语义是否影响它们留待后续提案单独论证；
- 不做天气接入、不做个人日历授权（各自独立提案）；
- 不做节假日数据的在线更新（随版本发布更新数据文件，MVP 够用）；
- 无新增屏幕与原型（建议卡复用既有交互，仅依据文案多一类来源）。

## 部署影响
- 是否需要部署：是
- 部署原因：free_weekend 计算语义变化与节假日数据文件随镜像发布
- 影响环境：本地 / 测试 / 预发 / 生产（生产部署仍需单独授权）
- 是否涉及数据迁移：否
- 是否需要回滚预案：是——应用回滚指回上一镜像即可（无 schema 变化）；节假日数据缺失时计算自动退化为现状语义，属安全降级
- 是否需要 smoke：是（复用既有 20 项，无新增 ID；free_weekend 计算正确性属 ST 职责，smoke 不验证——沿用部署方案 8.1 的既有约定）

## UI/UX 变更声明

```yaml
ui_impact: true
design_system_mode: generated
design_system_fallback_reason: ""
pages: []
description: 无新增屏幕。既有建议卡（core-02 增补）的依据区新增一类来源文案（如「因为 10/1–10/8 是国庆长假」），复用既有卡片交互与设计令牌，不新增原型屏。
```

## 变更概述
内置中国法定节假日与调休上班日数据文件（年份粒度 JSON，随镜像发布），为 free_weekend 时机计算与时机建议提供节假日事实：free_weekend 的触发日跳过调休上班的周末；提议生成的有界上下文加入节假日信息，建议理由与 `evidence` 可以引用（`kind=calendar`）。缺年份时计算退化为「不考虑节假日」的现状语义，不报错、不阻塞——这与产品「Agent 不可用也不阻塞记录」的降级哲学一致。服务端确定性校验、用户确认、调度器执行的三段边界完全不变，Scheduler 仍只扫描 wishes 的合法时机。

## 后续提案路线（本提案不做）
1. **天气数据源**：供应商选型 + 数据出境评估 + 建议依据（如「入冬那周大概率雨雪」）。
2. **个人日历授权**：OAuth + 敏感数据边界 + 忙闲查询，喂给「询问要克制」与建议。
3. **节假日对 season/month_day 语义的影响**：入冬日逢长假是否顺延，需产品论证后单独立项。


## 需要合并的 Delta 文件

### 1. deltas/api/wishes.yaml

- Delta 文件：`logos\changes\holiday-aware-timing\deltas\api\wishes.yaml`
- 目标目录：`logos\resources\api/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 2. deltas/prd/1-product-requirements/core-01-requirements.md

- Delta 文件：`logos\changes\holiday-aware-timing\deltas\prd\1-product-requirements\core-01-requirements.md`
- 目标目录：`logos\resources\prd\1-product-requirements/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 3. deltas/prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md

- Delta 文件：`logos\changes\holiday-aware-timing\deltas\prd\2-product-design\1-feature-specs\core-02-unhappened-place-design.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 4. deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md

- Delta 文件：`logos\changes\holiday-aware-timing\deltas\prd\3-technical-plan\1-architecture\core-01-architecture-overview.md`
- 目标目录：`logos\resources\prd\3-technical-plan\1-architecture/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 5. deltas/prd/3-technical-plan/2-scenario-implementation/core-S03-set-timing.md

- Delta 文件：`logos\changes\holiday-aware-timing\deltas\prd\3-technical-plan\2-scenario-implementation\core-S03-set-timing.md`
- 目标目录：`logos\resources\prd\3-technical-plan\2-scenario-implementation/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 6. deltas/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md

- Delta 文件：`logos\changes\holiday-aware-timing\deltas\prd\3-technical-plan\3-deployment\core-01-deployment-plan.md`
- 目标目录：`logos\resources\prd\3-technical-plan\3-deployment/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 7. deltas/scenario/core-00-orchestration-index.json

- Delta 文件：`logos\changes\holiday-aware-timing\deltas\scenario\core-00-orchestration-index.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 8. deltas/scenario/core-S03-timing.json

- Delta 文件：`logos\changes\holiday-aware-timing\deltas\scenario\core-S03-timing.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 9. deltas/test/core-S03-test-cases.md

- Delta 文件：`logos\changes\holiday-aware-timing\deltas\test\core-S03-test-cases.md`
- 目标目录：`logos\resources\test/`
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
   git add -A && git commit -m "docs(holiday-aware-timing): merge spec deltas"
   然后提示用户：按更新后的规格实现代码，代码完成后运行 `openlogos verify` 验收，验收通过后明确授权执行 `openlogos archive holiday-aware-timing`。
