# delta — core-01-architecture-overview.md（weather-data-source）

## ADDED — 5.8 天气数据源与位置偏好（weather-data-source）

```text
WeatherProvider（抽象，与 LLM/ASR 同模式）
  forecast(city: str, days: int = 14) -> list[WeatherFact] | None
    WeatherFact: {date, summary}（日级趋势，最多 14 天）
  OpenMeteoProvider（唯一实现）：geocoding + forecast 两段查询，
    base_url 由 WEATHER_BASE_URL 注入（默认官方端点），超时 5 秒、失败返回 None

位置来源（唯一）
  用户在 P6 声明的偏好 pref_key='location'（declared 行，加密存储，
  走 S08 既有撤回/删除体系）。未声明 → 不查询、上下文无天气事实。

查询时机与缓存
  仅 propose_timing 组装上下文时按需查询；进程内按城市缓存 6 小时
  （同一用户连续生成建议不重复打外部端点）。失败/超时 → None，
  上下文跳过天气事实（不阻塞、不重试队列）。

evidence 约定
  天气是瞬时预报，不写入 evidence（与「只存可追溯 ID 引用」的既有约定
  一致——预报变化后无持久条目可指）；建议理由文案可引用天气事实。
```

## MODIFIED — 七、外部依赖与测试策略

| 依赖 | 供应商形态 | 用于场景 | 测试策略 | 说明 |
|------|-----------|---------|---------|------|
| 天气 | Open-Meteo 兼容端点（`WEATHER_BASE_URL` 注入，无鉴权） | S03（时机建议上下文，weather-data-source） | `mock-service` | 本地天气 mock（geocoding + forecast 固定 JSON）；`weather_unavailable` 模式覆盖降级；未声明城市不发起请求 |

## MODIFIED — 九、场景清单（作为 Phase 3 Step 1 的输入）

| 编号 | 名称 | 优先级 | 参与方 |
|------|------|--------|--------|
| S01 | 新用户建立自己的未发生之地 | P0 | PWA、API、PG、LLM |
| S02 | 随手种下一个愿望并被理解 | P0 | PWA、API、PG、对象存储、ASR、LLM |
| S03 | 为一个愿望约定属于它的时机 | P0 | PWA、API、PG、Scheduler、Push、邮件、天气 |
| S04 | 风来了，开始第一小步 | P0 | PWA、API、PG、LLM、Scheduler |
| S05 | 回看未发生之地并重新整理（S05.1 浏览 / S05.2 整理） | P1 | PWA、API、PG |
| S06 | 把发生过的事写成一页记忆 | P0 | PWA、API、PG、对象存储、LLM |
| S07 | 唤回一个被安静放下的愿望 | P2 | PWA、API、PG |
| S08 | 管理偏好与可用时段 | P1 | PWA、API、PG、LLM、Scheduler |
| S09 | 先记一下并随手划掉 | P1 | PWA、API、PG |
| S10 | 管理提醒通道 | P1 | PWA、API、PG、Scheduler |
