# 合并指令

## 变更提案
- 提案名称：android-ux-crud
- 提案目录：logos/changes/android-ux-crud/

## 提案内容

# 变更提案：android-ux-crud

> module: core | created: 2026-09-07

## 变更原因

用户使用单机版后提出 9 条反馈，其中 8 条为功能/体验改进，1 条为产品咨询（第 9 条用户画像，另行给方案不在本批实现）。用户已就两个决策点拍板：愿望完成只留「收进书里」；随手记附件做到「文字备注 + 照片」。

## 收敛决策

| 决策点 | 本提案 | 理由 |
|--------|--------|------|
| 1 模型配置保存提示 | 保存成功后弹「已保存」Snackbar/提示 | 无反馈用户以为没存 |
| 2 日历弹窗确认 | 定时机写入日历时先弹系统运行时权限请求；授权后再次确认「是否写入日历」，用户同意才添加，否则仅应用内展示 | 不再静默写入，尊重用户控制 |
| 3 心语直接记想做的事 | 心语 record 阶段按「未来愿望 vs 当下轻事件」二分类：未来想做的事记入「未发生之地」（愿望），当下小事记入「随手记」（轻事件）；由模型输出 target 字段 | 用户要一个入口同时喂两处 |
| 4 无上下文时换建议 | ask 阶段：若检索结果为空，不回复「没找到」，而是理解意图主动给替代建议（按话题本身常识推荐） | 不显得死板 |
| 5 建议不局限清单 | ask 阶段：以个人记录为主（优先、置前），但允许在相关时拓展到清单外的常识性建议，并标注「这个是新的想法」 | 记录为主、拓展为辅 |
| 6 愿望完成简化 | 移除「保存」按钮，点「它已经发生了」→ 直接进记忆页编辑 → 仅「收进书里」一步完成并转 happened；退出自动存草稿（draft 状态保留） | 用户决策 |
| 7 三处增删改 | 愿望：已有改标题/原话与彻底删除，补「改标题」入口显性化；随手记：已有划掉/删除，补「编辑文本+备注」；已发生之书：补「删除记忆页」与「修改」 | 补齐 CRUD |
| 8 随手记附件 | LiteEvent 增 `note`（文字备注）与 `photos`（最多 9 张，本地文件路径）；详情弹窗支持编辑备注与从相册选照片 | 用户决策「文字+照片」 |
| 9 用户画像 | 本批不做；给方案见 proposal 附注 | 咨询性 |

## 变更类型
代码级（Android 单机端）

## 变更范围
- Room：LiteEventEntity 增 note/photos 字段（版本迁移 version 1→2）
- 心语：AnalysisService 增 record 二分类（愿望/轻事件）与 ask 的拓展建议提示词
- 日历：CalendarReminder 增「确认后写入」流程（UI 侧弹确认）
- UI：Settings 保存提示；MemoryPage 简化；三处增删改入口；LiteEvent 编辑/附件
- 测试：心语 record 二分类解析 UT；Room 迁移 UT

## 追加范围（用户 2026-09-07 追加三条）
1. 记忆页「收进书里」成功后直接跳转到已发生之书；
2. 已发生之书分「愿望 | 随手记」两个 Tab：愿望完成后入愿望区；随手记「划掉了」的条目进入随手记区（可继续加备注/照片），随手记区同样支持相关文本与照片；
3. 定时机表单改下拉框：法定节假日为单个下拉选择（含全部节假日），具体日期改为年/月/日三个下拉。

## 明确不做
- 不做用户画像数据表（第 9 条，另案）
- 不做照片云端同步（本地路径）
- 不改 backend/Web PWA

## 部署影响
- 是否需要部署：否（纯 Android）
- 数据迁移：Room 1→2（lite_events 加 note/photos，默认空，无需数据搬迁）

## UI/UX 变更声明

```yaml
ui_impact: true
design_system_mode: generated
design_system_fallback_reason: ""
pages: []
```

## 复用测试 ID
- UT-S09-01 — 轻事件创建/划掉语义（本次扩展 note/photos 字段，创建路径不变）
- UT-S02-02 — 种下结果 degraded 语义（心语 record 记愿望走同一降级）


## 需要合并的 Delta 文件

### 1. deltas/test/android-ux-crud-tests.md

- Delta 文件：`logos\changes\android-ux-crud\deltas\test\android-ux-crud-tests.md`
- 目标目录：`logos\resources\test/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

## 执行要求

1. 逐个 Delta 文件处理，每处理完一个报告修改摘要
2. 对于 ADDED 标记：在主文档的指定位置插入新内容
3. 对于 MODIFIED 标记：替换主文档中同名章节的内容
4. 对于 REMOVED 标记：从主文档中删除对应章节
5. 保持主文档的原有格式和风格
6. 如果主文档有"最后更新"时间戳，同步更新
7. 所有变更完成后，列出修改清单
8. 所有变更合并完成后，自动执行 git commit（告知用户，无需确认）：
   git add -A && git commit -m "docs(android-ux-crud): merge spec deltas"
   然后提示用户：按更新后的规格实现代码，代码完成后运行 `openlogos verify` 验收，验收通过后明确授权执行 `openlogos archive android-ux-crud`。
