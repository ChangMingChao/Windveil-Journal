# delta — core-00-information-architecture.md（s02-lite-conversion）

## MODIFIED — 二、场景 → 页面映射

> 全节替换（其中的「S09 范围说明」段落同步更新为含 S02 联动的版本——段落为正文粗体而非章节标题，故锚取父节）。

| 场景 | 名称 | 主页面 | 设计文档 |
|------|------|--------|---------|
| S01 | 新用户建立自己的未发生之地 | 首次体验流（温柔问题 → 输入）→ P2 | `core-01-seeding-design.md` |
| S02 | 随手种下一个愿望并被理解 | **P1 种下一个愿望** | `core-01-seeding-design.md` |
| S03 | 为一个愿望约定属于它的时机 | P3 愿望详情 → 时机选择半屏 | `core-02-unhappened-place-design.md` |
| S04 | 风来了，开始第一小步 | P3 愿望详情（对话区） | `core-02-unhappened-place-design.md` |
| S05.1 | 浏览未发生之地 | **P2 未发生之地** | `core-02-unhappened-place-design.md` |
| S05.2 | 重新整理一个愿望（改 / 停 / 放下） | P3 愿望详情 → 整理半屏 | `core-02-unhappened-place-design.md` |
| S06 | 把发生过的事写成一页记忆 | **P4 已发生之书** + P5 记忆页 | `core-03-book-of-happened-design.md` |
| S07 | 唤回一个被安静放下的愿望 | P2 →「安静放下」区 → P3 唤回半屏 | `core-02-unhappened-place-design.md` |
| S08 | 管理偏好与可用时段 | **P6 我的** →「它记得我什么」区 + P3 时机建议确认卡 | `core-05-preferences-availability-design.md` |
| S09 | 先记一下并随手划掉 | **P1 种下一个愿望**（「先记一下」区） | `core-06-lite-events-design.md` |
| S10 | 管理提醒通道 | **P6 我的**（「提醒通道」区） | `core-07-notification-channels-design.md` |

**S09 范围说明**：S09 复用 P1 页面（不开新路由），在主输入下方新增「先记一下」次级入口与轻事件列表区；交互规格见 `core-06-lite-events-design.md`。轻事件与愿望完全隔离：不进入未发生之地、不进提醒队列。**S02 联动已落地（s02-lite-conversion）**：near_term_todo 询问的第三选项「先记一下」可将误入愿望流程的轻意图转入轻事件，两个入口在 Agent 判断层形成闭环。
