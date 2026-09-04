# delta — core-01-deployment-plan.md（preferences-availability-timing）

## ADDED — 五·增补：本次变更（preferences-availability-timing）的迁移说明

| 项 | 内容 |
|----|------|
| 新增表 | `user_preferences`、`availability_windows`、`timing_proposals`——三张全新表，**不改动既有表的任何列**，属第五节「兼容要求」中最安全的加表类迁移 |
| 迁移形态 | 单个 Alembic revision 内三条 `CREATE TABLE` + 索引；SQLite 原生支持建表，无需 `batch_alter_table`，不触发重建表锁 |
| 数据回填 | 无。三张表从空表起步，无种子数据、无历史数据迁移 |
| 向后兼容 | 旧版应用代码不读不写这三张表，迁移后旧版本继续正常运行；`scheduler` 低频任务（提议过期、摘要生成）在新代码中才注册 |
| 迁移前备份 | 沿用第五节既有要求：先复制 `.db` 文件；本次迁移虽为加表，仍执行不豁免 |
| 回滚 | 应用回滚沿用上一镜像即可（旧代码不感知新表）；数据库回滚可恢复备份，也可保留新表不回滚——三张空表对旧代码无影响。`alembic downgrade -1` 可安全删除三表 |
| 表数量联动 | 部署后检查与 smoke 的表数量断言由 17 张更新为 **20 张**（索引数量以迁移产物实际为准，由「表数量与迁移版本相符」的相对断言覆盖） |
| 新增配置 | 无新增环境变量。提议有效期（7 天）与摘要周期（每日）先以服务常量落地，待需求 5.4 第 5/6 条确认后再提升为配置 |

## MODIFIED — 八、冒烟测试方案 > 8.2 必须覆盖的检查项（供 `test-writer` 生成 `SMOKE-*` 用例）

### 8.2 必须覆盖的检查项（供 `test-writer` 生成 `SMOKE-*` 用例）

| 类别 | 检查项 | 对应场景 / 端点 |
|------|--------|----------------|
| 健康检查 | 服务与数据库连通、调度心跳新鲜 | `GET /api/v1/health` |
| 配置与密钥 | 必需环境变量齐备；`APP_ENV` 正确；测试后门 404 | 第七节 6 / 11 |
| 数据库迁移 | `alembic current` 命中目标 revision；20 张表（原 17 张 + preferences-availability-timing 新增 3 张）与索引齐备 | 第五节 |
| 静态资源 | 首页、`manifest.webmanifest`、Service Worker 可取 | S05.1 的 `/garden` 入口 |
| 核心入口 | 匿名建号 → 拿到 access token | S01 Step 3，`POST /auth/anonymous` |
| 关键链路 | 种下一个愿望（文字）→ 出现在花园 | S02，`POST /wishes` + `GET /wishes` |
| 关键链路 | 约定一个时机 → 卡面出现时机文案 | S03，`PUT /wishes/{id}/timing` |
| 关键链路 | 手动触发一轮调度 → 提醒进入 outbox | 架构第八节；staging 用 `POST /api/test/scheduler/tick`，production 用 `docker compose run --rm scheduler --once` |
| 关键链路 | 标记已发生 → 生成记忆页 → 收进书里 → 出现在书架 | S06 全链路 |
| 关键链路（本次新增） | 声明一条偏好 → 能读回且来源为 declared；保存一条可用时段 → 能读回 | S08，`PUT /me/preferences` + `GET /me/preferences`、`POST /me/availability` + `GET /me/availability`；断言写响应不回显 value 明文 |
| 数据隔离 | 新建第二个匿名账号，用其 token 访问第一个账号的愿望与偏好，必须 404 | S05 EX-3.1 + S08 EX-19.1 |
| 加密落地 | 直接查库确认 `wishes.title_enc` 与 `user_preferences.value_enc` 不是可读明文 | `schema.sql` 加密约定 |
| 清理 | 彻底删除 smoke 账号的愿望 → 媒体对象与记录均不存在；删除偏好与时段 → 无残留 | S05.2 Step 25–31 + S08 Step 17–20 |
| 日志与监控 | 上述请求产生的日志含 `request_id`，且不含愿望原话与偏好值 | 第七节 12 |
