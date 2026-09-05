# delta — core-01-deployment-plan.md（s02-lite-conversion）

## ADDED — 五·增补：本次变更（s02-lite-conversion）的部署说明

| 项 | 内容 |
|----|------|
| 新增表 | 无。无数据库迁移 |
| 行为兼容 | `SeedWishResult.actions` 为枚举扩展（新增 `save_as_lite`）：旧前端不认识该值时自然不渲染按钮（响应向后兼容）；新前端 + 旧后端的组合会因端点 404 而隐藏选项——双向安全 |
| smoke | 不新增。SMOKE-core-10（种下）的 agent-mock 默认模式不返回 near_term_todo，行为不变 |
