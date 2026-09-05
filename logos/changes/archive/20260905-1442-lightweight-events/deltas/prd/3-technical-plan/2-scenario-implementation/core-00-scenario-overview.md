# delta — core-00-scenario-overview.md（lightweight-events）

## MODIFIED — 场景地图

| 编号 | 场景名称 | 分组 | 优先级 | Phase 1 | Phase 2 | Phase 3 时序图 | API 设计 | 编排测试 | 状态 |
|------|---------|------|--------|---------|---------|--------------|---------|---------|------|
| S01 | 新用户建立自己的未发生之地 | F01 | P0 | ✅ | ✅ | ✅ | ✅ | ✅ | 已交付 |
| S02 | 随手种下一个愿望并被理解 | F01 | P0 | ✅ | ✅ | ✅ | ✅ | ✅ | 已交付 |
| S03 | 为一个愿望约定属于它的时机 | F02 | P0 | ✅ | ✅ | ✅ | ✅ | ✅ | 已交付 |
| S04 | 风来了，开始第一小步 | F02 | P0 | ✅ | ✅ | ✅ | ✅ | ✅ | 已交付 |
| S05 | 回看未发生之地并重新整理 | F03 | P1 | ✅ | ✅ | ✅ | ✅ | ✅ | 已交付 |
| S06 | 把发生过的事写成一页记忆 | F04 | P0 | ✅ | ✅ | ✅ | ✅ | ✅ | 已交付 |
| S07 | 唤回一个被安静放下的愿望 | F03 | P2 | ✅ | ✅ | ✅ | ✅ | ✅ | 已交付 |
| S08 | 管理偏好与可用时段 | F02 | P1 | ✅ | ✅ | ✅ | ✅ | 🔲 | preferences-availability-timing |
| S09 | 先记一下并随手划掉 | F05 | P1 | ✅ | ✅ | ✅ | 🔲 | 🔲 | lightweight-events 本提案 |

> S08 编排测试已由 preferences-availability-timing 提案交付（core-S08-preferences-availability.json，4 flows）；地图状态以本提案视角标注。

## ADDED — 从时序图浮现的 API 清单（S09 增量）

| 端点 | 方法 | 来源步骤 | 说明 |
|------|------|---------|------|
| `/lite-events` | POST | S09 Step 9 | 记下一句话（纯写入，无 Agent） |
| `/lite-events` | GET | S09 Step 3 | open 列表（`include_done=true` 可追溯 done） |
| `/lite-events/{id}/done` | POST | S09 Step 15 | 划掉（status=done + closed_at） |
| `/lite-events/{id}` | DELETE | S09 Step 20 | 收走（硬删除） |

## MODIFIED — 场景索引

场景 S09（先记一下并随手划掉）由 lightweight-events 提案新增，使用全局 `scenario_counter.next_id=9`；功能分组 F05「轻量记录」随之建立。S09 的设计要点是**参与方刻意收窄**（无 LLM、无 Scheduler、无 Push/邮件）——参与方清单即「结构上无提醒路径」的证明。
