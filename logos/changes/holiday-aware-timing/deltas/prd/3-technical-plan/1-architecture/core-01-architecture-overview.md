# delta — core-01-architecture-overview.md（holiday-aware-timing）

## ADDED — 5.5 内置节假日数据源（holiday-aware-timing）

```text
数据形态
  文件：backend/app/data/holidays_{year}.json（随镜像发布，年份粒度，一年一文件）
  schema：{
    "year": 2026,
    "source": "数据出处说明（可追溯）",
    "updated_at": "文件生成时间",
    "holidays": { "YYYY-MM-DD": "节日名称", ... },   // 法定休假日（含长周末全部日期）
    "workdays":  { "YYYY-MM-DD": "调休说明", ... }    // 法定调休上班日（多为周末）
  }
  选择文件而非数据库：数据是全局公共事实，无用户数据参与、无写入路径、
  无需迁移与备份；随镜像发布天然版本化，回滚镜像即回滚数据。

加载与缓存
  按年份懒加载 + 进程内缓存；加载器只认 schema 字段，缺字段按空集处理。
  缺年份文件 → 返回空集（不是报错）：free_weekend 计算退化为「下一个周六/周日」
  的现状语义，提议上下文不含节假日事实，evidence 不出现 calendar 条目。
  与「Agent 不可用也不阻塞记录」同一降级哲学。

计算影响面（刻意收窄）
  free_weekend 的触发日：从「下一个周六/周日」变为「下一个非调休的周末日」——
  顺延扫描，命中第一个满足「周六或周日 且 不在 workdays 中」的日期；触发时刻沿用
  既有的上午约定，不改变。
  season / month_day / after_months 的触发日计算不变（见需求 5.3 的边界记录）。
  判定一律在服务端；LLM 只在建议理由中引用服务端提供的节假日事实。

更新机制（运维）
  每年官方公告发布后（通常 11–12 月）新增次年的 holidays_{year}.json 并随版本发布；
  发布前后过渡期按「缺年份退化」语义运行，无数据不阻塞。更新即发版，不做在线热更新。
```

**与其他节的关系**：S03 时机提议分支 P3 的有界上下文在组装时追加节假日事实（架构 5.4 第 1 层的输入扩展）；`TimingProposal.evidence` 的 `kind` 枚举扩展 `calendar`，条目 id 为数据文件标识（`holidays-{year}`），与「evidence 只存 ID 引用」的既有约定一致。

## MODIFIED — 七、外部依赖与测试策略

| 依赖 | 供应商形态 | 用于场景 | 测试策略 | 说明 |
|------|-----------|---------|---------|------|
| LLM | 任意 OpenAI 兼容 `/v1/chat/completions` | S01, S02, S04, S06, S03（时机建议，S08）, S08（偏好摘要） | `mock-service` | 本地起 OpenAI 兼容 mock，返回固定结构化 JSON；另提供「强制失败」开关以覆盖全部降级验收条件。时机建议的 mock 需支持返回 `propose_timing` 固定草稿与「不可用」两种模式 |
| ASR | 任意 OpenAI 兼容 `/v1/audio/transcriptions` | S02 | `mock-service` | 同上；失败模式用于验证「保留原始音频 + 可重试转写」 |
| Web Push | 浏览器推送服务（VAPID） | S03, S04 | `env-disable` + `test-api` | 测试环境关闭真实投递，只写 `reminder_outbox`；由 `GET /api/test/outbox?user_id=` 读取以断言周预算与去重 |
| 邮件 | SMTP 或供应商 API | S03（iOS 兜底） | `test-api` | `GET /api/test/latest-email?to={email}` 返回最近一封，用于验证兜底通道与文案 |
| 对象存储 | S3 兼容 | S02, S06 | 本地 MinIO 真实调用 | 不 mock：预签名 URL 的正确性本身就是需要验证的行为 |
| 时间 | 系统时钟 | S03, S04, S06, S08（建议过期扫描） | `fixed-value` | 时机到达、60 天停滞、发生日期早于种下日期、建议 7 天过期等断言必须可注入时间，服务层统一走 `Clock` 抽象 |
| 节假日数据 | 内置数据文件（随镜像发布，无网络请求） | S03（free_weekend 计算、时机建议依据） | `fixed-value` | 数据文件本身就是固定值：测试以受控的样例数据文件（含调休上班日与长周末）注入固定断言；「缺年份降级」用不存在的年份文件覆盖，不需要 mock 服务 |

**测试后门的安全约束**：`/api/test/*` 仅在 `APP_ENV=test` 时注册路由，生产构建下不存在该模块。
