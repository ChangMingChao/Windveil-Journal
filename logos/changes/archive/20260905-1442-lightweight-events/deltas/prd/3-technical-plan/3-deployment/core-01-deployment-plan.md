# delta — core-01-deployment-plan.md（lightweight-events）

## ADDED — 五·增补：本次变更（lightweight-events）的部署说明

| 项 | 内容 |
|----|------|
| 新增表 | `lite_events`——一张全新表，不改动既有表的任何列，加表类迁移 |
| 迁移形态 | 单个 Alembic revision（0009）一条 `CREATE TABLE` + 一个部分索引；SQLite 原生支持，无需 `batch_alter_table` |
| 数据回填 | 无。空表起步，无种子数据 |
| 向后兼容 | 旧代码不读不写这张表，迁移后旧版本继续正常运行 |
| 迁移前备份 | 沿用第五节既有要求，不豁免 |
| 回滚 | 应用回滚沿用上一镜像；`alembic downgrade -1` 可安全删除该表 |
| 表数量联动 | smoke 的表数量断言由 20 张更新为 **21 张**，`idx_` 索引 36 → **37** |
| 新增配置 | 无新增环境变量 |
| smoke 清单联动 | 新增 **SMOKE-core-21**（先记一下 → 划掉 → 收走 → 无残留），smoke 总数 20 → 21 |

## MODIFIED — 八、冒烟测试方案 > 8.2 必须覆盖的检查项（供 `test-writer` 生成 `SMOKE-*` 用例）

### 8.2 必须覆盖的检查项（供 `test-writer` 生成 `SMOKE-*` 用例）

| 类别 | 检查项 | 对应场景 / 端点 |
|------|--------|----------------|
| 健康检查 | 服务与数据库连通、调度心跳新鲜 | `GET /api/v1/health` |
| 配置与密钥 | 必需环境变量齐备；`APP_ENV` 正确；测试后门 404 | 第七节 6 / 11 |
| 数据库迁移 | `alembic current` 命中目标 revision；21 张表（20 张既有 + `lite_events`）与索引齐备 | 第五节 |
| 静态资源 | 首页、`manifest.webmanifest`、Service Worker 可取 | S05.1 的 `/garden` 入口 |
| 核心入口 | 匿名建号 → 拿到 access token | S01 Step 3，`POST /auth/anonymous` |
| 关键链路 | 种下一个愿望（文字）→ 出现在花园 | S02，`POST /wishes` + `GET /wishes` |
| 关键链路 | 约定一个时机 → 卡面出现时机文案 | S03，`PUT /wishes/{id}/timing` |
| 关键链路 | 手动触发一轮调度 → 提醒进入 outbox | 架构第八节；staging 用 `POST /api/test/scheduler/tick`，production 用 `docker compose run --rm scheduler --once` |
| 关键链路 | 标记已发生 → 生成记忆页 → 收进书里 → 出现在书架 | S06 全链路 |
| 关键链路（S08 增补） | 声明一条偏好 → 能读回且来源为 declared；保存一条可用时段 → 能读回 | S08，`PUT /me/preferences` + `GET /me/preferences`、`POST /me/availability` + `GET /me/availability`；断言写响应不回显 value 明文 |
| 关键链路（S09 增补） | 先记一下 → 能读回 → 划掉 → 收走 → 无残留；全程 outbox 无轻事件记录 | S09，`POST /lite-events` + `GET /lite-events` + `POST /{id}/done` + `DELETE /{id}`；顺带断言 `reminder_outbox` 中无该用户轻事件相关行 |
| 数据隔离 | 新建第二个匿名账号，用其 token 访问第一个账号的愿望、偏好与轻事件，必须 404 | S05 EX-3.1 + S08 EX-19.1 + S09 EX-22.1 |
| 加密落地 | 直接查库确认 `wishes.title_enc`、`user_preferences.value_enc` 与 `lite_events.text_enc` 不是可读明文 | `schema.sql` 加密约定 |
| 清理 | 彻底删除 smoke 账号的愿望 → 媒体对象与记录均不存在；删除偏好与时段 → 无残留 | S05.2 Step 25–31 + S08 Step 17–20 |
| 日志与监控 | 上述请求产生的日志含 `request_id`，且不含愿望原话、偏好值与轻事件文本 | 第七节 12 |
