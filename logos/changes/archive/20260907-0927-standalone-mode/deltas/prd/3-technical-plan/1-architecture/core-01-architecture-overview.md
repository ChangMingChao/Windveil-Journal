# delta — core-01-architecture-overview.md（standalone-mode）

## MODIFIED — 3.4 Android 原生客户端

### 3.4 Android 原生客户端（standalone-mode 改写）

Android 端收敛为**纯单机应用**，不再消费后端 API：

| 维度 | 选型 | 说明 |
|------|------|------|
| 本地数据 | Room 2.6（wishes / lite_events / memories 三表） | 单用户单库，schema 由既有 API 契约直译；状态机约束内建于 Repository |
| 网络 | Retrofit/OkHttp/TokenStore/CookieJar 移除 | 仅保留 HeartVoiceClient（用户自配的 OpenAI 兼容端点） |
| 分析 | AnalysisService（心语模型复用） | 愿望理解/一句追问/最小步骤/时机建议，使用期间静默执行；降级语义同后端（degraded 不阻塞） |
| 时机 | TimingCalculator（timing.py Kotlin 移植） | 六+1 类型同语义；节假日 JSON 随 APK 打包（assets）；以 UT-S03-55~58 为移植验收基准 |
| 提醒 | CalendarReminder（CalendarProvider） | 事件写入本地日历「未发生事件管理局」，系统到点提醒；未授权/失败降级为仅应用内展示；**邮件通道删除** |
| 账号 | 无 | 匿名建号/邮箱绑定/登录流程移除；数据可携带由 JSON 导出承担 |

边界：backend/ 与 Web PWA 保持现状（服务端模式仍可用）；Android 不做双模切换、不做端到端加密同步、不做后台自启分析。
