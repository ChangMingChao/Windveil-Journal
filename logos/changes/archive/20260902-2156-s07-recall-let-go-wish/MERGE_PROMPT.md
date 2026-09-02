# 合并指令

## 变更提案
- 提案名称：s07-recall-let-go-wish
- 提案目录：logos/changes/s07-recall-let-go-wish/

## 提案内容

# 变更提案：s07-recall-let-go-wish

> module: core | created: 2026-09-02

## 变更原因

S07「唤回一个被安静放下的愿望」是 Phase 1 就定义好的七个场景里**唯一没有落地**的一个：

- 需求文档第四节已写明触发条件、用户价值与主路径，但备注写着「P2 场景，验收条件在
  Phase 2 产品设计阶段随交互稿细化后补齐」——**验收条件至今为空**。
- 需求文档第五节「待确认事项」第 4 条就是「S07 是否提升至第一版范围内（当前为 P2）」，
  这条一直悬着。
- Phase 2 的信息架构第 33 行把它标为「P2 场景，本阶段仅占位」、设计文件「暂缺」；
  场景总览把它标为「未建模」。initial 轮明确按 S01–S06 建模，S07 不在任何 Batch 内。

也就是说：它不是欠账，是一条**被有意推迟、且推迟理由已经消失**的需求——S05.2 的
「安静放下」已经上线并通过验收，`let_go` 状态里现在真的会积累愿望，而用户没有任何
路径把它们拿回来。本提案作为项目 launched 之后的第一个变更提案，把这条路补上，
并据此关闭待确认事项第 4 条。

## 变更类型

需求级

理由：需要补写需求文档里 S07 的验收条件（当前为空），并解决第五节的待确认事项。
按变更传播规则，需求级变更的最小更新范围是全链路。

## 变更范围

- 影响的需求文档：
  - `prd/1-product-requirements/core-01-requirements.md` — 第四节 S07 补验收条件；
    第五节待确认事项第 4 条给出结论
- 影响的功能规格：
  - `prd/2-product-design/1-feature-specs/core-00-information-architecture.md` —
    第 33 行 S07 的「仅占位 / 设计文件暂缺」改为指向实际设计；状态机 `重新种下` 迁移补说明
  - `prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md` —
    新增 S07 小节（F03 的设计文件）
  - `prd/2-product-design/2-page-design/core-04-recall-let-go-prototype.html` — 新增原型
- 影响的业务场景：
  - `prd/3-technical-plan/2-scenario-implementation/core-00-scenario-overview.md` —
    S07 行由「未建模」改为已建模
  - `prd/3-technical-plan/2-scenario-implementation/core-S07-recall-let-go-wish.md` — 新增时序图
- 影响的技术架构：
  - `prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` —
    仅在本次决定纳入「种下时命中相似已放下记录」（见变更概述 Q2）时受影响，
    因为那需要给 Agent 增加一项能力；只做手动唤回则架构不变
- 影响的部署方案：无（新增一个端点与一次可空加列，不改拓扑、不改环境变量、不改发布顺序）
- 影响的 API：
  - `api/wishes.yaml` — 新增「重新种下」端点；`WishCard` / `WishDetail` 可能新增
    「放下时间」字段
- 影响的 DB 表：
  - `database/schema.sql` — `wishes` 预计新增一个可空列记录「安静放下的时间」
    （现在 `let_go` 只改状态、不留时间戳，阅读态无法呈现「你在什么时候放下了它」）
- 影响的编排测试：
  - `scenario/core-S07-recall.json` — 新增
  - `scenario/core-00-orchestration-index.json` — 登记新 flow
- 影响的测试用例：
  - `test/core-S07-test-cases.md` — 新增
- 影响的 smoke 测试：无。S07 是 P2 路径，不属于部署方案 §8.2 的关键链路清单；
  部署后仍跑既有 18 项 `SMOKE-core-*`，不新增 SMOKE ID

## 部署影响

- 是否需要部署：是
- 部署原因：新增 API 端点与（预计的）一次数据库加列，不部署则用户拿不到这条路径
- 影响环境：测试 / 预发（staging）；production 待人类另行确认
- 是否涉及数据迁移：是。预计为 `wishes` 新增一个**可空列**，属部署方案 §5 定义的
  向后兼容变更（加列可空），可被旧版应用代码安全运行；仍需按 §5 在迁移前备份 `.db`
- 是否需要回滚预案：是。沿用既有预案——应用层 `IMAGE_TAG` 指回上一个 tag，
  数据库层恢复迁移前的 `.db` 副本
- 是否需要 smoke：是（跑既有 18 项，不新增用例）

## UI/UX 变更声明

```yaml
ui_impact: true
design_system_mode: generated
design_system_fallback_reason: ""
pages:
  - id: let-go-zone
    prototype: core-04-recall-let-go-prototype.html
    description: 「安静放下」区列表——按放下时间倒序，卡片保留原话摘要，无任何挽留话术
  - id: recall-sheet
    prototype: core-04-recall-let-go-prototype.html
    description: 唤回半屏——当初的原话与首次种下时间、「重新种下」与「再放一会儿」两个出口
  - id: recall-timing
    prototype: core-04-recall-let-go-prototype.html
    description: 重新种下后的时机约定（复用 S03 的时机选择），含首次种下时间被保留的呈现
  - id: let-go-empty
    prototype: core-04-recall-let-go-prototype.html
    description: 空态——还没有放下过任何事时的文案，不出现「0」这类计数
```

设计令牌沿用项目既有的 `design-system.json`（由 ui-ux-pro-max 生成，
`design_system_mode: generated`），**不重新检索**：本次只是给已上线产品加一条子路径，
重新生成会得到一套不同的令牌并破坏视觉一致性。令牌副本随提案留存以便追溯。

## 变更概述

第一段是这条路径本身。「安静放下」区已经存在于花园的状态筛选里，但它现在是个只进不出的
地方。本次给它补上出口：打开一张放下的卡片，能看到当初写下的原话、首次种下的时间、
以及什么时候放下了它；一个「重新种下」把它送回酝酿，**首次种下时间原样保留**——
这是需求里点名的用户价值，「曾经放下的事不必从零开始」。半屏里同时留一个「再放一会儿」
的出口，让打开卡片这个动作本身不带压力。文案上继续遵守既有约束：不出现「放弃」
「未完成」，也不出现「你已经放下了 N 件事」这类计数。

第二段是两个需要你拍板的设计问题，它们会直接改变工作量，所以放在批准提案之前问：

**Q1｜重新种下之后落在哪个状态。** 需求写的是「状态回到『正在酝酿』并重新约定时机」，
但当前模型里「正在酝酿」的语义是**已经有时机**（`set_timing` 才会置 `brewing`）。
两个选项：(a) 唤回请求必须同时带上时机，一步到位回 `brewing`，代价是唤回半屏里塞进
一整套时机选择；(b) 唤回先回到「刚种下」，再走既有 S03 的设时机路径到 `brewing`，
两步但每步都很轻，且完全复用已验收的 S03。倾向 (b)——它让「唤回」和「约定时机」
各自保持单一职责，也避免在半屏里堆两件事。

**Q2｜第二个触发条件是否纳入本次范围。** 需求的触发条件写了两个：一是用户主动去
「安静放下」区翻回来（主路径已定义），二是「在种下新愿望时命中了已放下的相似记录」
（**没有定义主路径**）。后者需要给 Agent 加一项相似度判断能力、在 S02 的种下链路里
插一个确认分支、并处理「判错了怎么办」——成本明显高于前者，而且会牵动架构文档与
S02 的时序图。倾向本次只做第一个触发条件，把第二个作为独立提案；如果要一次做完，
影响范围里的「技术架构」与 S02 时序图需要一并纳入。

第三段是范围之外的事，写在这里以免误解：本提案不改「彻底删除」（仍不可恢复、仍二次确认），
不改 `let_go` 的进入路径（S05.2 已验收），也不引入任何「放下多久提醒你回来看看」的
主动召回——那与产品「不制造压迫感」的底线冲突。


## 需要合并的 Delta 文件

### 1. deltas/api/wishes.yaml

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\api\wishes.yaml`
- 目标目录：`logos\resources\api/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 2. deltas/database/schema.sql

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\database\schema.sql`
- 目标目录：`logos\resources\database/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 3. deltas/prd/1-product-requirements/core-01-requirements.md

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\prd\1-product-requirements\core-01-requirements.md`
- 目标目录：`logos\resources\prd\1-product-requirements/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 4. deltas/prd/2-product-design/1-feature-specs/core-00-information-architecture.md

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\prd\2-product-design\1-feature-specs\core-00-information-architecture.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 5. deltas/prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\prd\2-product-design\1-feature-specs\core-02-unhappened-place-design.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 6. deltas/prd/2-product-design/2-page-design/core-04-recall-let-go-prototype.html

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\prd\2-product-design\2-page-design\core-04-recall-let-go-prototype.html`
- 目标目录：`logos\resources\prd\2-product-design\2-page-design/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 7. deltas/prd/3-technical-plan/2-scenario-implementation/core-00-scenario-overview.md

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\prd\3-technical-plan\2-scenario-implementation\core-00-scenario-overview.md`
- 目标目录：`logos\resources\prd\3-technical-plan\2-scenario-implementation/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 8. deltas/prd/3-technical-plan/2-scenario-implementation/core-S07-recall-let-go-wish.md

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\prd\3-technical-plan\2-scenario-implementation\core-S07-recall-let-go-wish.md`
- 目标目录：`logos\resources\prd\3-technical-plan\2-scenario-implementation/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 9. deltas/scenario/core-00-orchestration-index.json

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\scenario\core-00-orchestration-index.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 10. deltas/scenario/core-S07-recall.json

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\scenario\core-S07-recall.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 11. deltas/test/core-S07-test-cases.md

- Delta 文件：`logos\changes\s07-recall-let-go-wish\deltas\test\core-S07-test-cases.md`
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
   git add -A && git commit -m "docs(s07-recall-let-go-wish): merge spec deltas"
   然后提示用户：按更新后的规格实现代码，代码完成后运行 `openlogos verify` 验收，验收通过后明确授权执行 `openlogos archive s07-recall-let-go-wish`。
