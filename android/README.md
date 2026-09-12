# 风起簿 — Android 原生 App（单机模式）

> 项目主体。最初由 three-tomato 按 `.three-tomato/requirements/`（PRD + OpenAPI 契约）生成，
> 现已迁至项目顶层 `android/` 目录独立演进，运行在**单机模式**：数据全部存于本地 Room，无账号、无服务端。

## 技术栈

| 维度 | 选择 |
|------|------|
| 语言 | Kotlin |
| UI | Jetpack Compose + Material 3（纸色主题，低饱和配色，无告警红） |
| 架构 | MVVM（StateFlow + ViewModel） |
| DI | Hilt |
| 网络 | OkHttp + Gson（仅心语直连用户自配的 HTTPS 模型端点，不经任何服务端） |
| 异步 | Coroutines |
| 本地存储 | Room（数据权威）+ DataStore（模型配置、心语对话历史） |
| 最低支持 | Android 8.0（minSdk 26），targetSdk 34 |

## 运行形态（重要）

- **无欢迎页、无匿名建号、无 token/refresh cookie**：启动直接进 `garden`（未发生之地）。
- **时机全部在端上计算**（`TimingCalculator` + assets 打包的节假日数据），`nextTriggerAt` 不再由服务端下发。
- **服务端契约代码不进发布包**：Retrofit 接口、契约模型、认证拦截器已整体移到 `app/src/test/`（保留契约回归测试），主源集仅保留 `HeartVoiceClient`。
- **心语（LLM）为用户自配**：在「我的 → 心语与模型」填写 HTTPS 接口地址、API Key、模型名；保存时强制 HTTPS 校验。模型未配置时一切功能照常降级（原话先保存、无追问、无建议）。
- **隐私与安全边界**：`allowBackup="false"`（API Key 与数据不随系统备份上云）；模型配置与对话历史仅存本机。

## 覆盖的产品场景

| 场景 | 页面 | 说明 |
|------|------|------|
| 进门即未发生之地 | `MainActivity` | startDestination = "garden"，无账号分流 |
| S02 随手种下一个愿望 | `SeedWishScreen` | 原话输入 + 心语一句追问；降级自动跳过轻问；「先记一下」原子转换为随手记（同文本轻事件） |
| S03 约定属于它的时机 | `WishDetailScreen` | 六种时机选项（端上计算）+「让它提个时候」；写日历前先取消旧事件，同 occurrence 去重防重复提醒 |
| S04 风来了，开始第一小步 | `WishDetailScreen` | 最小步骤（换一个更小的 / 做完了）+ 与 Agent 对话（历史气泡随愿望持久化，杀进程不丢） |
| S05 回看与整理 | `GardenScreen` + `WishDetailScreen` | 河流式列表、还不是现在 / 暂时不提醒 / 先放回酝酿 / 安静放下 / 彻底删除（二次确认） |
| S06 已发生之书 | `MemoryBookScreen` + `MemoryPageScreen` | 草稿→编辑→收进书里；全部区块可为空仍可发布 |
| S07 唤回被放下的愿望 | `WishDetailScreen` | let_go 状态提供「重新种下」 |
| S08 它记得我什么 | `SettingsScreen` | 用户画像（你说过的/我猜的，可删除） |
| S09 随手记 | `LiteEventsScreen` | 记下 / 划掉 / 收走，无提醒路径；编辑弹窗为朋友圈式（一段文字 + 3 列照片宫格，点 × 删单张，最多 9 张）；历史备注保留并在列表显示 |
| 心语对话 | `HeartVoiceScreen` | 意图分类（ask/record/chat）→ 记录或建议；对话历史持久化（杀进程不丢，取最近 8 轮作上下文）；回答可随时「停」 |

## 提醒通道：系统日历

- 授权日历权限后，约定时机时在自建的「风起簿」本地日历（ACCOUNT_TYPE_LOCAL）写入事件 + 准时提醒；未授权或失败降级为仅 App 内展示。
- 换时机/放下/删除/转换轻事件前都会先取消旧事件（URI 精确删除 + 描述前缀 `windveil:<wishId>` 兜底），不会重复提醒。
- 事件 URI 存在 `wishes.calendarEventUri` 独立字段（DB v4），不会被准备时间线 JSON 覆盖。
- ⚠️ 待真机验证：部分厂商 ROM 对 `ACCOUNT_TYPE_LOCAL` 行为差异较大，发布前建议至少覆盖 Pixel / 小米 / 华为 / 三星各一台，验证建日历、写事件、准时响铃、删事件四步。

## 备份与迁移

- 导出：`我的 → 数据 → 导出 JSON`，经系统保存器（SAF）选择保存位置，默认文件名 `windveil-backup-<时间戳>.json`；包含愿望、随手记（**照片以 base64 内嵌**）、已发生之书，带 `schema_version` 字段（当前 2）。
- 导入：按 ID 合并（同 ID 覆盖、新 ID 插入），整体在 Room 事务中执行并预校验 schema 版本；照片解 base64 后落本机新文件。v1 旧备份（无内嵌照片）只保留本机仍存在的路径。
- API Key 永不进入备份（备份只含业务数据；模型配置在 DataStore 中，且 `allowBackup=false`）。
- 愿望对话历史（`chat_messages` 表，DB v5）暂不进入备份：删愿望时随之清理，卸载重装不恢复。

## 构建与运行

1. 用 Android Studio（Hedgehog 以上）打开本目录（项目顶层 `android/`），等待 Gradle Sync。
2. 运行 `app` 到设备/模拟器；启动即进「未发生之地」，无需登录。
3. 单元测试：`./gradlew :app:testDebugUnitTest`（时机计算、LLM 严格解析、服务端契约回归）。
4. Room schema JSON 导出到 `app/schemas/`（`exportSchema = true`），改实体后对比/新增迁移，避免手写 SQL 漂移。
5. 发布：按顶层 [`CHANGE-PROCESS.md`](../CHANGE-PROCESS.md) §5.2 执行——递增 `versionCode`/`versionName`，执行
   `./gradlew :app:assembleDebug`，把 `app/build/outputs/apk/debug/app-debug.apk` 入库为
   `../release/风起簿-v<版本>.apk`（当前发布形态为 **debug 签名**；`release` 变体未配置签名，产物不可安装，不得入库），
   然后跑 `sh ../scripts/preflight.sh release` 并更新顶层 README 的「发布记录」台账。

## 已知边界（后续迭代项）

- 2027 节假日数据为推算版（`assets/holidays_2027.json` 的 `source` 已标注）：官方安排公布后替换该文件即可，`HolidayDataSource` 会自动扫描纳入；
- 语音种下（source=voice）：录音 UI 与上传管道未接入，可先用文字输入；
- 推送通知：提醒只走系统日历，FCM 未接入；
- 愿望/记忆页照片：仅随手记有照片流；
- Room 迁移自动化测试（MigrationTestHelper）具备条件（schema 已导出），尚未补测试用例；
- 依赖偏旧（AGP 8.5 / Kotlin 1.9.22 / Compose BOM 2024.02 / targetSdk 34）：升级 targetSdk 35+ 是上架 Google Play 的前置项，建议单独分支完整回归日历与照片选择器。

## 目录结构

```
app/src/main/java/com/windveil/journal/
├── WindveilApp.kt / MainActivity.kt
├── di/NetworkModule.kt            # 仅 Room 装配（网络栈已移出主源集）
├── data/
│   ├── local/                     # Room 实体/DAO、LlmConfigStore、HeartVoiceHistoryStore
│   ├── remote/HeartVoiceClient.kt # 心语直连客户端（OpenAI 兼容 /chat/completions）
│   ├── repository/StandaloneRepository.kt  # 唯一仓储：状态机/时机/日历/备份收口
│   └── domain → 见 domain/
├── domain/                        # TimingCalculator、CalendarReminder、AnalysisService、
│                                  # ExportService、HolidayDataSource、LlmJson（LLM 严格解析）
└── presentation/
    ├── theme/Theme.kt             # 纸色主题
    ├── navigation/WindveilNavHost.kt
    └── screens/                   # 各页面 + 对应 ViewModel

app/src/test/                      # 单元测试（含服务端契约回归：Models/ApiServices/WishesApiTest）
app/schemas/                       # Room schema JSON（v5）
```
