# 风起簿 · Windveil Journal

> Wait for the wind, then set forth. 等风来，再启程。

风是时机，簿是心愿册。Windveil 取「风掀起帷幕，心愿由此开启」。这是一个个人愿望陪伴产品，收集那些你不想错过的未来，并在你准备好时，陪你慢慢发生。

这里不是待办清单。它不计算逾期，不强调连续打卡，也不把未完成变成新的压力。适合放在这里的，是那些暂未开始、但值得被认真对待的事。

## 产品能力

- 直接进入「未发生之地」，用一句话随手种下一个愿望。
- 心语（用户自配的大模型）提炼愿望中的感受、隐含条件与最小下一步；模型未配置或不可用时仍会先保存原话。
- 用季节、月份日期、几个月后、节假日、空闲周末等方式约定时机；授权日历后写入系统日历，到点由系统提醒。
- 支持顺延、暂停、安静放下、重新种下与「先记一下」（转轻事件）。
- 随手记（轻事件）支持备注与照片（存本机）。
- 愿望发生后可以写成记忆页，长期沉淀为「已发生之书」。
- **独立模式（唯一模式）**：数据完全存于本地（Room），无账号、无服务端；支持 JSON 备份导出/导入（含随手记照片，可跨设备迁移）。

## 项目形态

本项目已完全收敛为 **Android 原生 App 的单机形态**：无后端、无账号体系。历史 Web 后端/前端/部署内容已删除（可从 git 历史找回）；OpenAPI 契约仅作为需求参考保留在 `.three-tomato/requirements/`，对应的 Retrofit 契约代码已整体移到测试源集（不进发布包）。

## 技术栈

| 维度 | 选择 |
| --- | --- |
| 语言 | Kotlin |
| UI | Jetpack Compose + Material 3（纸色主题，低饱和配色） |
| 架构 | MVVM（StateFlow + ViewModel） |
| DI | Hilt |
| 异步 | Coroutines |
| 本地存储 | Room（数据权威）+ DataStore（模型配置、心语对话历史） |
| 网络 | OkHttp + Gson（仅心语直连用户自配的 HTTPS 模型端点） |
| 图片 | Coil |
| 版本 | minSdk 26（Android 8.0）/ targetSdk 34 |

## 目录结构

```text
android/                      Android 原生 App（项目主体）
  app/src/main/java/com/windveil/journal/
    data/local/               Room 实体/DAO、模型配置与心语历史存储
    data/remote/              HeartVoiceClient（心语直连客户端）
    data/repository/          StandaloneRepository（唯一仓储，业务规则收口）
    domain/                   时机计算、节假日、系统日历提醒、备份导出、LLM 解析
    presentation/             主题、导航与各页面
  app/src/test/               单元测试（时机计算、LLM 解析、服务端契约回归）
  app/schemas/                Room schema JSON（迁移比对用）
.three-tomato/requirements/   产品 PRD 与 OpenAPI 契约（需求参考）
.three-tomato/config.yaml     three-tomato 生成配置存档说明
```

## 构建与运行

1. 用 Android Studio（Hedgehog 以上）打开 `android/` 目录，等待 Gradle Sync。
2. 运行 `app` 到设备/模拟器；启动即进「未发生之地」（garden），无需登录。
3. 单元测试：

   ```bash
   cd android
   ./gradlew :app:testDebugUnitTest
   ```

详细的场景、页面与已知边界说明见 [`android/README.md`](android/README.md)。
