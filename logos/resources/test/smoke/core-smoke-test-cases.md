# core: 部署后冒烟测试用例

> 模块：core｜上游：`../../prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` 第七节（12 项部署后检查）与第八节（13 项 smoke 覆盖清单）
> 结果写入：`logos/resources/verify/smoke-results.jsonl`（由 `logos.config.json → smoke.result_path` 指定）

## 一、冒烟测试范围

| 环境 | 覆盖范围 | 说明 |
|------|----------|------|
| `local` | 健康检查、迁移、核心入口、关键链路 | 开发自测，允许用 `agent-mock` |
| `staging` | 全部 18 项 | 发布门禁，必跑必过 |
| `production` | 全部 18 项 | 人类明确授权后执行；数据自建自清，不留残留 |

执行前提（来自部署方案 8.1）：

- smoke 自建一个匿名账号，结束时**彻底删除**其全部数据，可重复执行且不依赖前次残留。
- LLM / ASR **不 mock**，但**降级路径也算通过**——理由见部署方案 8.3，断言分层体现在 SMOKE-core-09。
- 不注入时钟。`/api/test/clock` 在非 test 环境不存在，smoke 只验证「能触发一轮扫描」，不验证「时机计算正确」（那是 ST 的职责）。

## 二、冒烟测试用例

### 2.1 健康检查与配置

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-01 | 健康检查接口可访问且数据库连通 | 部署方案 §7-1 | local / staging / production | 服务已部署 | `GET /api/v1/health` | 200 且 `status="ok"`、`database="ok"` |
| SMOKE-core-02 | 调度进程存活 | §7-2 | staging / production | scheduler 已启动 | 读同一响应的 `scheduler_heartbeat_age_seconds` | 非 null 且 < 900 |
| SMOKE-core-03 | 必需环境变量齐备 | §7-11 | staging / production | — | 执行 `ops/check-env.sh` | 全部必需变量非空；`ENCRYPTION_KEY` 长度符合预期；**不打印任何密钥值** |
| SMOKE-core-04 | 测试后门在非 test 环境不存在 | §7-6 | staging / production | — | `GET /api/test/outbox?user_id=<uuid>` | 404（路由未注册） |
| SMOKE-core-05 | 数据库文件与 PRAGMA 正确 | §7-8、§3.4 | staging / production | 可访问 `.db` 文件 | 查 `PRAGMA foreign_keys` / `journal_mode`；检查文件在持久卷内且权限 600 | 依次为 1 / `wal`；文件路径匹配 `DATABASE_URL`，权限 600 |

### 2.2 数据库迁移与隔离

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-06 | 迁移版本与本次发布一致 | §7-3 | local / staging / production | 迁移已执行 | `alembic current` | 等于目标 revision |
| SMOKE-core-07 | 关键表齐备 | §8.2 迁移项 | staging / production | — | 查 `sqlite_master` 中 21 张表与全部索引是否存在 | 21 张表（20 张既有 + `lite_events`）与索引全部存在（不再有扩展检查——加密在应用层） |
| SMOKE-core-08 | 数据隔离守卫生效 | §7-7 | staging / production | 已建两个 smoke 账号 A、B | 用 B 的 token 请求 A 的愿望详情与列表 | 均 404 / 空列表；启动日志含 `owner_guard installed` |


### 2.3 核心入口与关键链路

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-09 | 匿名建号可用 | §8.2 核心入口 | local / staging / production | 服务健康 | `POST /api/v1/auth/anonymous` | 201 且返回 access_token；`onboarded_at` 非空 |
| SMOKE-core-10 | 种下一个愿望并出现在花园（降级也算通过） | §8.2 关键链路、§8.3 分层断言 | local / staging / production | 已有 smoke 账号 | `POST /api/v1/wishes {source:text,text:"smoke：想去看海"}` → `GET /api/v1/wishes` | **必须通过**：201 且该愿望出现在列表、`title` 非空、`original_text` 与提交一致。**仅告警**：`degraded==true` 时 PASS 但报告标注「Agent 降级，检查 LLM_BASE_URL / LLM_API_KEY」 |
| SMOKE-core-11 | 约定一个时机 | §8.2 关键链路 | local / staging / production | 已有 seeded 愿望 | `PUT /api/v1/wishes/{id}/timing {type:after_months,after_months:1}` | 200；`state="brewing"`；`timing.label` 非空；`timing.next_trigger_at` 非 null |
| SMOKE-core-12 | 触发一轮调度且提醒进入 outbox | §8.2 关键链路 | staging / production | 存在一条已到期时机（smoke 直接把 `next_trigger_at` 置为过去） | staging：`POST /api/test/scheduler/tick`；production：`docker compose run --rm scheduler --once` | 返回统计中 `scanned>=1` 且 `enqueued>=1`；`reminder_outbox` 出现该愿望的记录 |
| SMOKE-core-13 | 记忆页全链路 | §8.2 关键链路 | local / staging / production | 已有愿望 | `POST /wishes/{id}/happened` → `POST /memories/{id}/publish` → `GET /memories` | 201 → 200 → 书架含该页；`wishes.state="happened"`；`lived_pages>=1` |
| SMOKE-core-14 | 数据隔离：跨账号访问返回 404 | §8.2 数据隔离 | staging / production | 两个 smoke 账号 | 用 B 的 token 请求 A 的 `GET /wishes/{id}` | **404**（不是 403，也不是 200） |
| SMOKE-core-15 | 预签名上传可用 | §7-9 | staging / production | 已有 smoke 账号 | `POST /media/upload-url` → PUT 一个 1KB 音频 → `POST /media/{id}/complete` | 201 → 200 → 204；`media.status="ready"` |

### 2.4 静态资源与传输

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-16 | 静态站点与 PWA 资源可取 | §7-4 | staging / production | web 已部署 | `GET /`、`GET /manifest.webmanifest`、`GET /sw.js` | 三者均 200；manifest 可解析为 JSON |
| SMOKE-core-17 | HTTPS 与证书有效 | §7-5 | staging / production | Caddy 已签发证书 | 检查证书剩余有效期；`curl -I http://<host>` | 剩余 >14 天；HTTP 返回 301 到 HTTPS |

### 2.5 加密、日志与清理

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-18 | 加密落地、日志无明文、smoke 数据已清理 | §8.2 加密落地 / 日志与监控 / 清理、§7-12 | staging / production | SMOKE-core-10 已执行 | 查 `wishes.title_enc` 原始字节；抽查最近 100 条应用日志；`DELETE /wishes/{id}?confirm=true` 后复查 | `title_enc` 为 BLOB 且不含 `想去看海` 子串；日志含 `request_id` 且不含该子串；删除后愿望、媒体对象与 `memories` 均不存在 |

### 2.6 S08 基础链路（preferences-availability-timing 增补）

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-19 | 偏好声明与读取（含不回显断言） | 部署方案 §8.2 关键链路（S08 增补） | local / staging / production | 已有 smoke 账号 | `PUT /api/v1/me/preferences {pref_key:"companion", value:"smoke：更想和朋友一起"}` → `GET /api/v1/me/preferences` | PUT 200 且响应**不含 value 明文**；GET 返回该条 `source="declared"`、`confidence=100`、value 与提交一致；直查 `user_preferences.value_enc` 为 BLOB 且不含「smoke：」子串（与 SMOKE-core-18 同型的加密抽查） |
| SMOKE-core-20 | 可用时段保存与读取 | 部署方案 §8.2 关键链路（S08 增补） | local / staging / production | 已有 smoke 账号 | `POST /api/v1/me/availability {weekday:5, start_minute:540, end_minute:720}` → `GET /api/v1/me/availability` → `DELETE /api/v1/me/availability/{id}` | 201 → 列表含该条（`weekday=5`）→ 204；重复 DELETE 返回 404；清理后无残留（并入 smoke 数据自清理） |

### 2.7 S09 基础链路（lightweight-events 增补）

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-21 | 先记一下 → 划掉 → 收走 → 无残留 | 部署方案 §8.2 关键链路（S09 增补） | local / staging / production | 已有 smoke 账号 | `POST /api/v1/lite-events {text:"smoke：今晚吃火锅"}` → `GET /lite-events` → `POST /{id}/done` → `DELETE /{id}` → 查 `reminder_outbox` | 201 且回显 text → 列表含该条（status=open）→ done 200 → 204；重复 DELETE 404；**`reminder_outbox` 中无任何轻事件相关行**（结构上无提醒路径的 smoke 级体现）；直查 `lite_events.text_enc` 为 BLOB 且不含「火锅」子串 |

## 三、覆盖度校验

- [x] 健康检查：SMOKE-core-01、02
- [x] 核心入口：SMOKE-core-09
- [x] 数据库迁移：SMOKE-core-06、07
- [x] 静态资源：SMOKE-core-16
- [x] 配置与密钥：SMOKE-core-03、04、05
- [x] 关键链路：SMOKE-core-10、11、12、13、15、19、20、21
- [x] 日志与监控：SMOKE-core-18
- [x] S09 基础链路：SMOKE-core-21
- [x] 表数量断言联动：SMOKE-core-07 更新为 21 张表
- [x] 部署方案 §7 的 12 项检查：1→01、2→02、3→06、4→16、5→17、6→04、7→08、8→05、9→15、10→10（仅告警）、11→03、12→18
- [x] 部署方案 §8.2 的 15 项清单（含 S08/S09 增补）：逐项映射至上表，无遗漏


## 四、给 code 阶段的要求（本轮新增 18 个 SMOKE-*，必须闭环）

1. 实现 `scripts/smoke-core.sh`（或等效 runner），**覆盖全部 21 个 `SMOKE-core-*` ID**（含本轮新增的 SMOKE-core-21），ID 原样使用不得改写。
2. runner 必须把每条结果写入 `logos/resources/verify/smoke-results.jsonl`，格式见 `logos/spec/test-results.md`。
3. `logos.config.json → smoke.command` 必须能执行该 runner；推荐接入统一 `scripts/run-smoke.js` dispatcher 自动发现 `scripts/smoke-*`。
4. SMOKE-core-10 必须实现**分层断言**：链路通过即 PASS，`degraded==true` 只写 warning 字段，不改判 FAIL。
5. SMOKE-core-19 必须断言**写响应不回显 value 明文**与 `value_enc` 密文落库两件事——这是 S08 隐私红线的 smoke 级体现。
6. SMOKE-core-21 必须断言**outbox 无轻事件相关行**——「结构上无提醒路径」的 smoke 级体现。
7. code 阶段完成前必须运行 smoke 覆盖预检，确认 21 个 ID 均不在 uncovered cases 中。
8. runner 结束时必须清理 smoke 账号的全部数据（含 SMOKE-core-19/20/21 产生的偏好、时段与轻事件），失败也要清理。
