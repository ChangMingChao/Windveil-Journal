# 风起簿 · Windveil Journal

> Wait for the wind, then set forth. 等风来，再启程。

风是时机，簿是心愿册。Windveil 取「风掀起帷幕，心愿由此开启」。这是一个个人愿望陪伴产品，收集那些你不想错过的未来，并在你准备好时，陪你慢慢发生。

这里不是待办清单。它不计算逾期，不强调连续打卡，也不把未完成变成新的压力。适合放在这里的，是那些暂未开始、但值得被认真对待的事。

## 产品能力

- 直接进入「未发生之地」，用一句话随手种下一个愿望。
- 心语（用户自配的大模型）提炼愿望中的感受、隐含条件与最小下一步；模型未配置或不可用时仍会先保存原话。
- 用季节、月份日期、几个月后、节假日、空闲周末等方式约定时机；授权日历后写入系统日历，到点由系统提醒。
- 支持顺延、暂停、安静放下、重新种下与「先记一下」（转轻事件）。
- 随手记与愿望都支持照片（存本机）；随手记另有文字备注。
- 愿望发生后可以写成记忆页，长期沉淀为「已发生之书」。
- **独立模式（唯一模式）**：数据完全存于本地（Room），无账号、无服务端；支持 JSON 备份导出/导入（含随手记、愿望与记忆页照片，可跨设备迁移）。

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

## 发布记录

发布包一律入库到 `release/`，文件名恒为 `release/风起簿-v<版本>.apk`（`.gitignore` 对 `release/*.apk` 例外）。
**每个版本必须同时具备三件东西：递增的 `versionCode`/`versionName`、与该 commit 同批入库的 APK、指向该 commit 的附注 tag。**
本表是唯一权威版本台账，`sh scripts/preflight.sh release` 会核对它与源码是否自洽。发布与提交流程见 [`CHANGE-PROCESS.md`](CHANGE-PROCESS.md)。

| 版本 | 日期 | 交付物 | versionCode | git tag | 状态 |
| --- | --- | --- | --- | --- | --- |
| v0.4.1 | 2026-09-13 | [`release/风起簿-v0.4.1.apk`](release/风起簿-v0.4.1.apk) | 7 | v0.4.1 | 最新版本：记忆页照片（DB v7，备份格式 v4，收进书里继承愿望照片）；⚠️ 真机回归待执行 |
| v0.4.0 | 2026-09-12 | [`release/风起簿-v0.4.0.apk`](release/风起簿-v0.4.0.apk) | 6 | v0.4.0 | 愿望支持照片（DB v6，备份格式 v3）；真机回归状态未回填 |
| v0.3.0 | 2026-09-12 | [`release/风起簿-v0.3.0.apk`](release/风起簿-v0.3.0.apk) | 5 | v0.3.0 | SAF 导出 / 设置页日历授权 / 发布导航 / 2027 节假日（推算版）/ 时机今天边界 / 心语可中断；真机回归状态未回填 |
| v0.2.2 | 2026-09-09 | [`release/风起簿-v0.2.2.apk`](release/风起簿-v0.2.2.apk) | 4 | ❌ 缺失 | ⚠️ **交付物漂移**（包由 `b51133f` 构建，不含聊天历史 DB v5 等）：已由 v0.3.0 重发解决 |
| v0.2.1 | 2026-09-09 | `release/风起簿-v0.2.1.apk`（已移除） | 3 | ❌ 缺失 | 历史版本 |
| v0.2.0 | 2026-09-08 | `release/风起簿-v0.2.0.apk`（已移除） | 2 | ⚠️ v0.2.0 | tag 打在 `6f20d3a`（仅改版本号），该树里取不到 v0.2.0 的包 |
| v0.1.0 | 2026-09-07 | `release/风起簿-v0.1.0.apk`（已移除） | 1 | ❌ 缺失 | 首个可下载版本 |

已发布包的 sha256 指纹（用户报障时先比对指纹，确认复现对象一致）：

| 版本 | sha256 |
| --- | --- |
| v0.4.1 | `0fbaac5df8ade5a8ba294c0bb501fcc6fbb40c92ec46c0b32ce77a508093171b` |
| v0.4.0 | `00f6f1980d175e16f4b22fcc2bb2b50d5ede9af50f61718db14a9c5d556f16c3` |
| v0.3.0 | `27541134367ef646e52c3beba7ac3f9f2faf6621bf9442916570a2640d3b5bc7` |
| v0.2.2 | `ac69bfc476064f0a16521d41faa610a5a1cd1c900acf80e55efca4d7298623c8` |
| v0.2.1 | `e172457d239da370078889b27ef04c3e7d9c2347f714946bd278cb4b6b6badcd` |
| v0.2.0 | `485b75b6b37dd6dd96701beb44989968280e2a118a362c8989b2cab112b5d8db` |
| v0.1.0 | `0d3b779d1ec1a1b57b7f70c401f42b1f7236c4eba2d844fc8e1a33465e907899` |

> 历史版本的包文件已不在工作区，可用
> `git cat-file blob <commit>:release/风起簿-v<版本>.apk > 风起簿-v<版本>.apk` 取回。

## 构建与运行

1. 用 Android Studio（Hedgehog 以上）打开 `android/` 目录，等待 Gradle Sync。
2. 运行 `app` 到设备/模拟器；启动即进「未发生之地」（garden），无需登录。
3. 单元测试：

   ```bash
   cd android
   ./gradlew :app:testDebugUnitTest
   ```

详细的场景、页面与已知边界说明见 [`android/README.md`](android/README.md)。
