# delta — core-00-information-architecture.md（lightweight-events）

## MODIFIED — 二、场景 → 页面映射

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

**S07 范围说明**：S07 复用 P2「安静放下」状态筛选与 P3 详情页，只新增唤回半屏；本次只处理用户主动唤回，不把「种下时命中相似已放下记录」纳入 S02。

**S08 范围说明**：S08 的常驻入口在 P6「我的」（新增「它记得我什么」区：偏好 + 可用时段）；时机建议（TimingProposal）的确认卡出现在 P3 详情页时机区，交互规格并入 `core-05-preferences-availability-design.md`，P3 侧改动见 `core-02-unhappened-place-design.md` 的对应增补。S08 不新增顶层路由，避免设置类页面抢夺导航注意力。

**S09 范围说明**：S09 复用 P1 页面（不开新路由），在主输入下方新增「先记一下」次级入口与轻事件列表区；交互规格见 `core-06-lite-events-design.md`。轻事件与愿望完全隔离：不进入未发生之地、不进提醒队列。

## MODIFIED — 三、页面结构与路由

```text
/                       P1 种下一个愿望（首页 = 唯一输入入口；含「先记一下」区，S09）
/welcome                首次体验流（S01，仅新用户；完成后不再进入）
/garden                 P2 未发生之地（主界面，花园视图 / 河流视图可切换）
/garden?state=<状态>    P2 按状态筛选（deep-link，URL 反映当前视图）
/wish/:id               P3 愿望详情（含 Agent 对话、时机、准备过程）
/wish/:id#timing        P3 时机选择半屏
/wish/:id#timing-advice P3 时机建议确认半屏（S08：展示建议、理由、置信度与确认/拒绝）
/wish/:id#tidy          P3 重新整理半屏（改 / 停 / 放下 / 彻底删除）
/wish/:id#recall        P3 唤回半屏（仅 `let_go` 状态可用，S07）
/book                   P4 已发生之书（按时间倒序的书页列表）
/book/:id               P5 单页记忆（可编辑补充）
/me                     P6 我的（隐私说明、它记得我什么 [S08]、提醒通道、导出、注销）
/me#remembered          P6「它记得我什么」区（偏好 + 可用时段，S08 常驻入口）
```

导航层级（底部固定导航，仅 3 项 + 1 个主动作）不变。S09 不新增路由：轻事件列表就是 P1 主输入下方的一块区域，「记一下」与「种下」同屏共存、各走各的存储。

## MODIFIED — 5.1 提醒预算（对应需求文档指标「每周提醒 ≤ 3 条」）

### 5.1 提醒预算（对应需求文档指标「每周提醒 ≤ 3 条」）

| 规则 | 具体行为 |
|------|---------|
| 全局周预算 | 每用户每自然周最多 3 条主动提醒（Web Push 或邮件，合计计数） |
| 超额处理 | 按用户设置时机的先后顺序顺延到下一周；被顺延的卡片在 P2 内以柔光标记呈现，不发推送 |
| 单卡去重 | 同一张卡的同一次时机只发 1 条，用户已在应用内看到该时机则不再补发 |
| 禁止合并 | 不得将多张卡合并为一条清单式提醒（如「你有 5 件事待处理」） |
| 停滞关心 | 「正在发生」满 60 天无动作时最多 1 条，且计入周预算 |
| 静默通道 | 用户可在 P6 关闭推送仅保留邮件、或全部关闭；关闭后不再有任何应用内催促标记 |
| 时机建议不是提醒（S08） | Agent 的时机建议（TimingProposal）只存在于应用内「待确认」状态，不进入 outbox、不发送推送或邮件、不占用周预算；确认后走既有时机与预算链路 |
| 轻事件无提醒路径（S09） | 轻事件（lite_events）在结构上不进入提醒发件箱、不被调度器扫描、不占用周预算——「不占额度」由数据结构保证，而非行为约定 |

## MODIFIED — 六、追溯

| Phase 1 场景 | Phase 2 设计文档 | 原型 |
|--------------|-----------------|------|
| S01, S02 | `core-01-seeding-design.md` | `core-01-seeding-prototype.html` |
| S03, S04, S05.1, S05.2 | `core-02-unhappened-place-design.md` | `core-02-unhappened-place-prototype.html` |
| S06 | `core-03-book-of-happened-design.md` | `core-03-book-of-happened-prototype.html` |
| S07 | `core-02-unhappened-place-design.md`（S07 增补） | `core-04-recall-let-go-prototype.html` |
| S08 | `core-05-preferences-availability-design.md` | `core-05-preferences-availability-prototype.html` |
| S09 | `core-06-lite-events-design.md` | `core-06-lite-events-prototype.html` |

本文档不单独配原型：信息架构与全局规则通过上述 6 份原型共同体现。
