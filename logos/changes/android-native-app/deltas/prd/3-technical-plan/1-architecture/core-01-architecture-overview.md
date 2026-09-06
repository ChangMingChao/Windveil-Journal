# delta — core-01-architecture-overview.md（android-native-app）

## ADDED — 3.4 Android 原生客户端（android-native-app 增补）

### 3.4 Android 原生客户端

| 维度 | 选型 | 理由 | 备选方案 |
|------|------|------|---------|
| 来源 | three-tomato（android-generator）按既有 PRD + API 契约生成 | 用户决策；生成物在 `.three-tomato/output/android/`，与 `frontend/` 物理隔离、零侵入 | 人工原生重写（成本高） |
| 语言 / UI | Kotlin + Jetpack Compose + Material 3 | AI 数据集大、声明式 UI；纸色低饱和主题延续「不制造焦虑」设计原则 | Flutter、React Native |
| 架构 | MVVM（ViewModel + StateFlow + Repository） | 与 Android 官方推荐一致 | MVI、Clean Architecture |
| 依赖注入 | Hilt | Android 生态事实标准 | Koin |
| 网络 | Retrofit + OkHttp + Gson | 对应既有 REST/JSON 契约（协议保留原则）；DTO 用 `@SerializedName` 承载 snake_case | Ktor |
| 认证 | Bearer access token（DataStore）+ httpOnly refresh cookie（持久化 CookieJar）+ 401 自动刷新重放 | 严格对齐 auth.yaml 的自管 JWT 方案，客户端不读取 refresh 内容 | — |
| 运行时 | minSdk 26 / targetSdk 34 | 覆盖 Android 8.0+ | — |

边界：Android 端**只消费**既有 API（auth/wishes/memories/lite-events/media/system），不引入任何服务端变更；构建产物不进入部署单元（仍为静态站点 + api + scheduler 三个运行单元）；FCM 推送、语音/照片直传 UI、新设备登录界面为后续迭代项。
