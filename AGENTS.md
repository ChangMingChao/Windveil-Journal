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
2. 构建产物（`build/`、`.gradle/`、`local.properties`、`.idea/`）不入库。
3. 功能变更请同步更新 `android/README.md` 的场景/边界说明。
4. 提交信息使用 conventional commits（`feat(android): ...` / `fix(android): ...`）。

## 迭代与发布流程（强制，无例外）

**任何改动都必须走 [`CHANGE-PROCESS.md`](CHANGE-PROCESS.md)**（含变更分级、关卡、红线与 commit 模板）。要点：

1. 动手前先定级（L0 文档 / L1 代码 / L2 数据与外部契约 / L3 版本发布），按级别过关，判定有歧义就高不就低。
2. 每完成一个可独立验证的最小单元，立刻 `git add <显式路径>` + `git commit`。
   **禁止 `git add -A` / `git add .` / `git commit -a`**——必须显式列路径（`release/*.apk` 是 `.gitignore` 的例外，更要显式 add）。
3. **版本更新（改 `versionCode`/`versionName`、换 `release/*.apk`、打 tag）必须在同一次操作内完成
   `git add` + `git commit` + `git tag -a`**，不允许"文件改好了但没提交"，也不允许只改文件不递版本号。
   标准动作序列见 CHANGE-PROCESS.md §5.2。
4. 提交信息必须含 `变更` / `影响面`（grep 命令 + 命中数）/ `验证`（设备 + 日期 + 结果）三段，模板见附录 D；
   裸提交（如只写 `V0.2.2`）与混提交（功能 + 重构 + 改名塞一个 commit）属红线。
5. 提交前跑 `sh scripts/preflight.sh quick`，发布前跑 `sh scripts/preflight.sh release`。
   仓库已通过 `core.hooksPath=.githooks` 挂上 pre-commit 钩子，违规提交会被拦下。
6. 关卡没过（单测失败、真机回归未做、交付物与源码不一致）就如实说"未通过"，
   不得用"应该没问题""理论上可行"结案；同时更新 `README.md` 的「发布记录」台账。
