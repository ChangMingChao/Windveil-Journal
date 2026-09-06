# 合并指令

## 变更提案
- 提案名称：android-native-app
- 提案目录：logos/changes/android-native-app/

## 提案内容

# 变更提案：android-native-app

> module: core | created: 2026-09-06

## 变更原因

用户要求：本地安装 [three-tomato](https://github.com/trsoliu/three-tomato) 插件，并将当前项目转换为安卓应用代码。three-tomato 是一个 skills.sh 兼容的 AI 技能包，输入**需求文档**，按配置生成目标平台的原生代码（Android 为 Kotlin + Jetpack Compose）。

本项目的输入条件已经齐备：`prd/1-product-requirements/core-01-requirements.md` 提供完整需求，`logos/resources/api/*.yaml` 提供既有后端 REST API 契约。因此 Android 端不是重写业务，而是**按既有 PRD + API 契约生成原生客户端**，与现有 React/PWA 前端平行。

### 关键澄清（插件能力边界）

three-tomato 的输入是需求文档，**不是**「把现有 React 代码逐文件翻译成 Kotlin」。它读取 PRD / API 规格，生成结构完整的 Android 原生工程。本提案将 PRD 与 API yaml 作为输入注入插件，保证生成的 Android 端与现有 Web 端在数据模型、API 调用上保持一致。

## 收敛决策（请重点确认）

| 决策点 | 本提案 | 理由 |
|--------|--------|------|
| 输入来源 | 既有 PRD（core-01-requirements.md）+ 6 个 API yaml | 项目规格即真相源，避免插件凭空发明需求 |
| 目标平台 | 仅 `android`（Kotlin + Jetpack Compose + MVVM + Retrofit） | 用户明确只要安卓；插件默认 AI 友好技术栈 |
| 输出位置 | `.three-tomato/output/android/`（全新目录） | 生成物与现有代码物理隔离，零侵入 |
| 对现有代码影响 | 零修改（frontend/、backend/ 不动） | 转换是「新增平行客户端」，不是替换 |
| 后端对接 | Android 端按既有 REST API（auth/wishes/memories/lite-events/media/system）直连现有后端 | API 契约已存在，不做接口级变更 |
| 插件安装位置 | 用户级 `~/.agents/skills/three-tomato`（已完成） | 不污染项目仓库 |

## 变更类型
代码级

新增一个由插件生成的 Android 原生工程目录与插件工作目录配置。不修改任何现有需求/设计/接口/DB 文档，不改既有前后端代码。规格侧仅在架构文档补记「Android 原生客户端」的存在与技术栈，保持文档与代码一致。

## 变更范围
- 影响的需求文档：无（需求不变，只是新增一个端）
- 影响的功能规格：无
- 影响的业务场景：无（场景复用 S01–Sxx 既有定义）
- 影响的 API：无（Android 端消费既有 API，无接口变更）
- 影响的 DB 表：无
- 影响的编排测试：无（编排测试针对后端 API，与客户端技术栈无关）
- 新增的目录：
  - `.three-tomato/config.yaml` — 插件配置（platforms: [android]，指向 PRD/API）
  - `.three-tomato/requirements/` — 需求输入副本
  - `.three-tomato/output/android/` — 生成的 Android 工程（Kotlin + Compose）
  - `.three-tomato/reports/` — 平台对照 / 迁移说明

## 明确不做（本提案边界）
- 不做 iOS / 鸿蒙 / 小程序等其他平台（插件支持但用户只要 Android）；
- 不修改 frontend/（React PWA 继续存在并可用）；
- 不修改 backend/ 与任何 API 契约；
- 不在本提案内做 Android 端的应用商店发布、签名配置的真机验证（构建运行需要用户本机 Android Studio / SDK）；
- 插件生成代码的人工调优（如登录态存储细节）留到生成后按需迭代。

## 部署影响
- 是否需要部署：否
- 部署原因：Android 端为本地生成的客户端工程，不涉及服务端变更；现有后端 API 不变
- 影响环境：无
- 是否涉及数据迁移：否
- 是否需要回滚预案：否（删除 `.three-tomato/` 目录即完全回退）
- 是否需要 smoke：否

## UI/UX 变更声明

```yaml
ui_impact: false            # 现有 Web 端界面不变；Android UI 由插件按 PRD 生成，属新增端
design_system_mode: generated
design_system_fallback_reason: ""
pages: []
```

## 变更概述

1. 配置 three-tomato 插件工作目录 `.three-tomato/`：目标平台仅 android，技术栈 Kotlin + Jetpack Compose + MVVM + Retrofit + Coroutines（插件默认 AI 友好栈），输入指向项目既有 PRD 与 API yaml。
2. 执行插件生成流程，产出完整 Android 工程到 `.three-tomato/output/android/`：项目结构、Compose UI 页面（对应 PRD 场景：种愿望、愿望列表、时机建议、已发生之书等）、数据模型（对齐 wishes/memories/lite-events/media/auth 契约）、Retrofit API 客户端、MVVM 业务逻辑、单元测试与 README。
3. 生成平台对照与迁移说明报告；在架构文档补记 Android 原生客户端一节。
4. 输出构建运行说明（Android Studio 打开、依赖现有后端 base_url 配置）。


Android 侧对应测试产物：AND-UT-01 ~ AND-UT-07（已写入 logos/resources/verify/test-results.jsonl，source: .three-tomato/output/android）

## 复用测试 ID
- UT-S05-02 — Android 未发生之地列表消费同一游标分页契约（GardenScreen + MockWebServer AND-UT-02 覆盖同一行为）
- UT-S05-03 — Android 越权 404 WISH_NOT_FOUND 错误映射与后端契约一致（AND-UT-06 同源断言）
- UT-S02-01 — Android 种下愿望请求体与端点路径符合契约（AND-UT-05 同源断言）
- UT-S02-02 — Android 种下结果 degraded 语义（question 为 null 时跳过轻问）
- UT-S09-01 — Android 随手记轻事件的创建/划掉契约解析（AND-UT-04 同源断言）


## 需要合并的 Delta 文件

### 1. deltas/prd/1-product-requirements/core-01-requirements.md

- Delta 文件：`logos\changes\android-native-app\deltas\prd\1-product-requirements\core-01-requirements.md`
- 目标目录：`logos\resources\prd\1-product-requirements/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 2. deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md

- Delta 文件：`logos\changes\android-native-app\deltas\prd\3-technical-plan\1-architecture\core-01-architecture-overview.md`
- 目标目录：`logos\resources\prd\3-technical-plan\1-architecture/`
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
   git add -A && git commit -m "docs(android-native-app): merge spec deltas"
   然后提示用户：按更新后的规格实现代码，代码完成后运行 `openlogos verify` 验收，验收通过后明确授权执行 `openlogos archive android-native-app`。
