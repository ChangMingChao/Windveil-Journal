# 风起簿 · Windveil Journal

> Wait for the wind, then set forth. 等风来，再启程。

风是时机，簿是心愿册。Windveil 取「风掀起帷幕，心愿由此开启」。这是一个个人愿望陪伴产品，收集那些你不想错过的未来，并在你准备好时，陪你慢慢发生。

这里不是待办清单。它不计算逾期，不强调连续打卡，也不把未完成变成新的压力。适合放在这里的，是那些暂未开始、但值得被认真对待的事。

## 产品能力

- 匿名建立私人空间，用一句话随手种下一个愿望。
- Agent 提炼愿望中的感受、隐含条件与最小下一步；模型不可用时仍会先保存原话。
- 用季节、月份、空闲周末、疲惫信号等方式约定时机，让提醒在对的时候出现。
- 支持顺延、暂停、安静放下与重新种下。
- 愿望发生后可以写成记忆页，长期沉淀为「已发生之书」。
- 独立模式：数据完全存于本地（Room），无需服务端即可使用；支持 JSON 导出/导入。

## 项目形态

本项目现已完全收敛为 **Android 原生 App**，位于 [`android/`](android/)。历史上的 Web 后端（FastAPI）、Web 前端（React）、部署与 OpenLogos 方法论文档已删除，如需追溯可查看 git 历史。

## 技术栈

| 维度 | 选择 |
| --- | --- |
| 语言 | Kotlin |
| UI | Jetpack Compose + Material 3（纸色主题，低饱和配色） |
| 架构 | MVVM（StateFlow + ViewModel） |
| DI | Hilt |
| 异步 | Coroutines |
| 本地存储 | Room（独立模式数据）+ DataStore（token/偏好） |
| 网络 | Retrofit + OkHttp + Gson（服务端契约见 `.three-tomato/requirements/*.yaml`） |
| 图片 | Coil |
| 版本 | minSdk 26（Android 8.0）/ targetSdk 34 |

## 目录结构

```text
android/                      Android 原生 App（项目主体）
  app/src/main/java/com/windveil/journal/
    data/local/               Room 实体/DAO、TokenStore、CookieJarStore
    data/remote/              Retrofit 接口与契约模型
    data/repository/          独立模式与在线模式仓储
    domain/                   时机计算、节假日、日历提醒、导出等服务
    presentation/             主题、导航与各页面
.three-tomato/requirements/   产品 PRD 与 OpenAPI 契约（需求参考）
.three-tomato/config.yaml     three-tomato 生成配置存档说明
```

## 构建与运行

1. 用 Android Studio（Hedgehog 以上）打开 `android/` 目录，等待 Gradle Sync。
2. 运行 `app` 到设备/模拟器；首次启动点「开始」即建立匿名个人空间。
3. 单元测试：

   ```bash
   cd android
   ./gradlew :app:testDebugUnitTest
   ```

详细的场景、页面与已知边界说明见 [`android/README.md`](android/README.md)。
