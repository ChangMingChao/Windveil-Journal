## MODIFIED — 二、冒烟测试用例 > 2.2 数据库迁移与隔离

### 2.2 数据库迁移与隔离


| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-06 | 迁移版本与本次发布一致 | §7-3 | local / staging / production | 迁移已执行 | `alembic current` | 等于目标 revision |
| SMOKE-core-07 | 关键表齐备 | §8.2 迁移项、S07 `0007_s07_recall` 迁移 | staging / production | — | 查 `sqlite_master` 中 17 张表与 29 个索引是否存在 | 17 张表、29 个索引全部存在（不再有扩展检查——加密在应用层） |
| SMOKE-core-08 | 数据隔离守卫生效 | §7-7 | staging / production | 已建两个 smoke 账号 A、B | 用 B 的 token 请求 A 的愿望详情与列表 | 均 404 / 空列表；启动日志含 `owner_guard installed` |

