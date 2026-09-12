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

## 编码风格：Ponytail 懒人阶梯

> 规则合并自 [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)（MIT），仅作编码风格约束；
> 不改变上文「迭代与发布流程」的任何关卡与红线，冲突时以上文流程为准。

以"懒人资深开发者"的方式写代码：懒 = 高效，不是马虎。最好的代码是从未写出的代码。

写任何代码之前，先理解问题（读完任务、端到端走一遍真实调用链），再逐级检查"懒人阶梯"，停在第一个成立的级别：

1. 这需要被造出来吗？（YAGNI：不需要就不写）
2. 代码库里已经有了？复用现成的 helper / util / 模式，不要重写。
3. 标准库能做？用标准库。
4. 平台原生功能能覆盖？用原生的。
5. 已装的依赖能解决？用它。
6. 能写成一行吗？就写一行。
7. 到这一步才动手：写出能工作的最小实现。

**修 bug 修根因，不修症状**：用户报告的只是症状。用 grep 找出所改函数的全部调用方，在共享函数里修一次——在那里加一个守卫，比在每个调用方各打一个补丁的 diff 更小；只修工单点名的那条路径，兄弟调用方还会继续坏。

规则：

- 不做任何没有被明确要求的抽象。
- 能不加新依赖就不加。
- 不写没人要的样板代码。
- 删除优先于新增；朴素优先于炫技；文件数越少越好。
- 最短的可用 diff 胜出——前提是先理解问题；在错误位置上的最小改动不是懒，是第二个 bug。
- 质疑复杂需求："你真的需要 X 吗，Y 是不是已经覆盖了？"
- 两个标准库方案体量相同时，选边界条件更正确的那一个：懒 = 代码更少，不是算法更脆。
- 刻意简化且切掉了真实一角、有已知上限的做法（全局锁、O(n²) 扫描、朴素启发式），用 `ponytail:` 注释标明上限与升级路径。

**这些方面不许懒**：理解问题（选级之前先读全任务、走通真实链路；不看懂就动手的小 diff 只是化装成效率的懒）、信任边界上的输入校验、防止数据丢失的错误处理、安全、无障碍、真机所需的校准（平台永远不等于规格理想值：时钟会漂移、传感器会有偏差）、以及任何被明确要求的东西。

懒代码缺了检查就是没写完：非平凡逻辑必须留下**一个**可运行的检查——最小的、逻辑坏了就会失败的东西（assert 自检或一个小测试文件；不引入框架、不搭 fixture）。平凡的一行改动不需要测试。
