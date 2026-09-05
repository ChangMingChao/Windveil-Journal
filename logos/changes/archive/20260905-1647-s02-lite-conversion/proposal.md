# 变更提案：s02-lite-conversion

> module: core | created: 2026-09-05

## 变更原因
来自 lightweight-events 提案路线图的第 1 步：「S02 联动——near_term_todo 询问式确认（EX-18.2）加第三选项『先记一下』，让『这更像这几天要办的事』的输入自然落入轻事件表」。

当前 S02 的行为：用户输入被判为 near_term_todo（当下日程）时，Agent 以询问确认，给两个选择——「就当成未来的事」（keep_as_future）与「删掉它」（delete）。**中间态缺失**：既不想让这句话变成有提醒压力的愿望、也不想丢掉它——恰好是 S09 轻事件存在的意义。两个入口（种下 / 先记一下）在 Agent 判断这一层还没有形成闭环。

## 收敛决策（请重点确认）
| 决策点 | 本提案 | 理由 |
|--------|--------|------|
| 选项形态 | EX-18.2 的 `actions` 数组新增 `save_as_lite`（第三选项），文案「先记一下」 | 复用既有询问通道与响应结构，前端只是多一个按钮 |
| 转换语义 | 新端点 `POST /wishes/{id}/convert-to-lite`：**同一事务内删除 wish 行（含照片关联与 pending 提醒）+ 新建同文本 lite_event** | 「底层共享存储」的落地方式；wish 的 Agent 理解结果不迁移（轻事件不需要），照片不迁移（轻事件无媒体） |
| 端点边界 | 仅 `seeded` 状态可转换（未约定时机、未开始推进）；`brewing` 及以后拒绝 | 已确认时机的愿望转轻事件等于变相弃约，需要单独的产品论证 |
| 幂等与隔离 | 转换后原 wish_id 彻底消失（404）；新 lite_event 归属同一用户 | 与 S05.2 彻底删除、S09 EX-22.1 同策略 |
| 额度 | 转换不产生任何提醒；lite_event 无提醒路径（S09 既有保证） | 不新增额度语义 |

## 变更类型
接口级

S02 询问响应的枚举扩展 + 一个转换端点（含同事务删除语义）+ EX-18.2 验收条件修订。不改数据表（lite_events 已存在）。因改变已上线的 S02 询问行为，按全链路处理但范围最小。

## 变更范围
- 影响的需求文档：
  - `prd/1-product-requirements/core-01-requirements.md` — S02 增补验收条件（2 条）、5.3「不做」清单中「轻事件的 Agent 理解与建议」条目修订（理解联动已落地，建议仍不做）
- 影响的功能规格：
  - `prd/2-product-design/1-feature-specs/core-06-lite-events-design.md` — S09 增补：来自 S02 转换的轻事件（来源标注与文案）
- 影响的信息架构：
  - `prd/2-product-design/1-feature-specs/core-00-information-architecture.md` — S09 范围说明更新（联动已落地）
- 影响的 API：
  - `api/wishes.yaml` — `SeedWishResult.actions` 枚举扩展 `save_as_lite`；新增 `POST /wishes/{id}/convert-to-lite`
- 影响的 DB 表：
  - 无
- 影响的测试用例：
  - `test/core-S02-test-cases.md` — EX-18.2 第三选项的 UT/ST 增量
- 影响的编排测试：
  - `scenario/core-S02-seed-wish.json` — 新增 1 个 flow；`scenario/core-00-orchestration-index.json` — 更新 coverage
- 影响的部署方案：
  - `prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` — 无迁移；行为兼容说明

## 明确不做（本提案边界）
- 不做照片/语音迁移（转换的轻事件只保留文本）；
- 不做反向转换（lite → wish，见 lightweight-events 路线第 3 步）；
- 不做自动转换（判定为 near_term_todo 时仍由用户选择，Agent 不代劳）；
- `brewing` 及以后状态不可转换。

## 部署影响
- 是否需要部署：是
- 部署原因：新端点 + S02 询问响应枚举扩展
- 影响环境：本地 / 测试 / 预发 / 生产（生产部署仍需单独授权）
- 是否涉及数据迁移：否
- 是否需要回滚预案：是——应用回滚沿用上一镜像；旧前端不认识 save_as_lite 选项时自然不渲染（响应枚举扩展向后兼容）
- 是否需要 smoke：不新增——转换链路属 ST 层；既有 SMOKE-core-10（种下）在 mock 的 near_term_todo 模式关闭时行为不变

## UI/UX 变更声明

```yaml
ui_impact: true
design_system_mode: generated
design_system_fallback_reason: ""
pages: []
description: 无新增屏幕。S02 询问卡（EX-18.2）的选项区由两个变三个：「就当成未来的事」「先记一下」「删掉它」，复用既有卡片交互。
```

## 变更概述
当 Agent 把一条输入判定为 near_term_todo（当下日程）时，EX-18.2 的确认询问在原有两个选项之外新增第三选项「先记一下」（`save_as_lite`）。用户选择后，`POST /wishes/{id}/convert-to-lite` 在同一事务内删除该 wish 行（级联照片关联与 pending 提醒）并新建同文本的 `lite_event`——两个入口（种下 / 先记一下）在 Agent 判断层形成闭环：轻意图从判断到落库全程无提醒压力。仅 `seeded` 状态可转换；转换后原 wish_id 彻底消失，新轻事件归属同一用户。

## 后续提案路线（本提案不做）
1. **转换时迁移照片**：wish 的照片随转换迁入轻事件（需要轻事件支持媒体，先不做）。
2. **反向转换**：lite → wish（lightweight-events 路线第 3 步）。
