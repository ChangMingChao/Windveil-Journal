# AI Assistant Instructions — 风起簿（Windveil Journal）

## 语言策略（最高优先级）

本项目文档与交流语言为**中文**。
你的所有输出——包括生成的文档、代码注释、回复消息——必须使用中文。

## 项目概况

「未发生事件管理局」— 个人愿望陪伴产品：收集那些你不想错过的未来，并在你准备好时，陪它们慢慢发生。

本项目已完全收敛为 **Android 原生 App**（历史 Web 后端/前端/部署已删除，可从 git 历史找回）。

## 项目结构

- `android/` — Android 原生 App（项目主体，独立可运行，详见 `android/README.md`）
- `.three-tomato/requirements/` — 产品 PRD 与 OpenAPI 契约（App 的需求来源，作为需求参考保留）
- `.three-tomato/config.yaml` — three-tomato 生成配置存档说明

## 技术栈

- Kotlin + Jetpack Compose + Material 3
- MVVM（StateFlow + ViewModel）、Hilt、Coroutines
- Room 本地存储（独立模式）、DataStore
- Retrofit + OkHttp（网络契约保留，见 `.three-tomato/requirements/*.yaml`）
- minSdk 26 / targetSdk 34

## 工作约定

1. 修改 App 代码前，先阅读 `android/README.md` 了解架构与页面结构。
2. 构建产物（`build/`、`.gradle/`、`local.properties`）不入库。
3. 功能变更请同步更新 `android/README.md` 的场景/边界说明。
4. 提交信息使用 conventional commits（`feat(android): ...` / `fix(android): ...`）。
