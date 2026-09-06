# 未发生事件管理局 — Android 原生客户端

> 由 three-tomato（android-generator）按 `logos/resources/prd/1-product-requirements/core-01-requirements.md`
> 与 `logos/resources/api/*.yaml` 契约生成。变更提案：`logos/changes/android-native-app/`。

## 技术栈

| 维度 | 选择 |
|------|------|
| 语言 | Kotlin |
| UI | Jetpack Compose + Material 3（纸色主题，低饱和配色，无告警红） |
| 架构 | MVVM（StateFlow + ViewModel） |
| DI | Hilt |
| 网络 | Retrofit + OkHttp + Gson |
| 异步 | Coroutines |
| 本地存储 | DataStore（access token）+ 持久化 CookieJar（refresh token） |
| 最低支持 | Android 8.0（minSdk 26），targetSdk 34 |

## 覆盖的产品场景

| 场景 | 页面 | 说明 |
|------|------|------|
| S01 新用户建立未发生之地 | `WelcomeScreen` | 点「开始」匿名建号，无表单；温柔问题按契约允许整体跳过 |
| S02 随手种下一个愿望 | `SeedWishScreen` | 原话输入 + Agent 一句追问；降级（degraded）自动跳过轻问；支持「就当成未来的事 / 先记一下」 |
| S03 约定属于它的时机 | `WishDetailScreen` | 六种时机选项 + 「让它提个时候」（采纳/先不定）；next_trigger_at 全部由服务端计算 |
| S04 风来了，开始第一小步 | `WishDetailScreen` | 最小步骤（换一个更小的 / 做完了，If-Match 乐观锁）+ 与 Agent 对话（chat/amend/assist/fatigue） |
| S05 回看与整理 | `GardenScreen` + `WishDetailScreen` | 河流式列表、还不是现在 / 暂时不提醒 / 先放回酝酿 / 安静放下 / 彻底删除（confirm 二次确认） |
| S06 已发生之书 | `MemoryBookScreen` + `MemoryPageScreen` | 草稿→编辑→收进书里；全部区块可为空仍可发布 |
| S07 唤回被放下的愿望 | `WishDetailScreen` | let_go 状态提供「重新种下」 |
| S08 它记得我什么 | `SettingsScreen` | 偏好（你说过的/我猜的、撤回/删除）、可用时段管理 |
| S09 随手记 | `LiteEventsScreen` | 记下 / 划掉 / 收走，无提醒路径 |
| S10 提醒通道 | `SettingsScreen` | 推送/邮件开关，全关=完全安静（pending 顺延保留由服务端保证） |

## 构建与运行

1. 用 Android Studio（Hedgehog 以上）打开本目录（`.three-tomato/output/android/`），等待 Gradle Sync。
2. 指向后端：`app/build.gradle.kts` 里的 `API_BASE_URL`：
   - 模拟器访问本机后端：`http://10.0.2.2:8000/`
   - 真机联调：改为局域网地址 `http://<你的IP>:8000/`（后端需允许明文时，在 manifest 加 `android:usesCleartextTraffic="true"`，仅限开发）
3. 运行 `app` 到设备/模拟器；首次启动点「开始」即建立匿名个人空间。
4. 单元测试：`./gradlew :app:testDebugUnitTest`（契约反序列化 + MockWebServer API 行为测试）。

## 认证实现（对应 auth.yaml 契约）

- access token（Bearer，15 分钟）：存 DataStore，由 `AuthInterceptor` 附加；
- refresh token（httpOnly Cookie，30 天）：客户端不读取内容，由 `CookieJarStore` 原样保存并在 `/auth/refresh` 时带回；
- 401 时 `TokenAuthenticator` 自动刷新并重放一次；刷新失效则回到欢迎页。

## 已知边界（后续迭代项）

- 语音种下（source=voice）：媒体预签名直传接口已生成（`MediaApi`），录音 UI 与上传管道未接入，可先用文字输入；
- 推送通知：FCM 接入未包含在本批（服务端通道开关已可管理）；
- 照片上传（愿望/记忆页）：接口已生成，选择器 UI 未接入；
- 时机建议历史页（listTimingProposals）已具备 API，未做独立界面。

## 目录结构

```
app/src/main/java/com/windveil/journal/
├── WindveilApp.kt / MainActivity.kt
├── di/NetworkModule.kt            # Hilt 网络装配（含刷新专用通道）
├── data/
│   ├── local/TokenStore.kt        # access token + 冷启动判定
│   ├── local/CookieJarStore.kt    # httpOnly refresh cookie 持久化
│   ├── remote/Models.kt           # 契约数据模型（对齐 6 个 OpenAPI yaml）
│   ├── remote/ApiServices.kt      # Retrofit 接口（operationId 一一对应）
│   ├── remote/AuthInterceptor.kt / TokenAuthenticator.kt
│   └── repository/                # Auth / Wish / Memory / Preference / LiteEvent
└── presentation/
    ├── theme/Theme.kt             # 纸色主题
    ├── navigation/WindveilNavHost.kt
    └── screens/                   # 8 个页面 + 对应 ViewModel
```
