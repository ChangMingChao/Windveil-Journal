# 变更提案：user-profile

> module: core | created: 2026-09-07

## 变更原因

用户确认实施第 9 条方案的代码化：在 Room 加 preferences 表，心语分析时把「有空时间、运动偏好、饮食倾向」等提炼成条目（含来源分层），建议时读取。原则：**从用户已给的信息里提炼，而不是反复开口问**。

## 收敛决策

| 决策点 | 本提案 | 理由 |
|--------|--------|------|
| 数据层 | Room `preferences` 表（prefKey/value/source/confidence/createdAt），DB 2→3 | 与后端 S08 偏好体系同构 |
| 来源分层 | `declared`（用户在心语里明说的）/ `inferred`（模型从多条记录推断的） | S08 红线：分层才能撤回 |
| 提炼时机 | 心语每次对话后**顺带**提炼（一次对话最多新增 2 条，去重） | 静默完成、不打扰 |
| 提问策略 | 不主动提问（本批）；模型只在对话自然涉及偏好时提炼 | 避免收集癖 |
| 建议生效 | ask 阶段把偏好条目注入上下文，且要求优先依据偏好给排序（如「在减肥」→ 自助靠后） | 画像价值落地 |
| 用户控制 | 「我的 → 心语与模型」下新增「用户画像」二级页：可查看全部条目、删除任意条（declared/inferred 都可删） | S08 可查看可删除红线 |
| 隐私 | 条目只存本地 Room，仅随 ask 上下文发往用户自配模型 | 沿用心语边界 |

## 变更类型
代码级（Android 单机端）

## 变更范围
- Room：新表 + 迁移 2→3
- AnalysisService：对话后提炼 prompt + JSON 解析；askPrompt 增偏好区块
- HeartVoiceViewModel：对话后静默提炼、去重写入
- SettingsScreen：用户画像二级页
- 测试：提炼解析 UT、迁移 UT

## 明确不做
- 不做主动提问/引导问卷（后续提案）
- 不做偏好云端同步
- 不改 backend/Web PWA

## 部署影响
- 是否需要部署：否
- 数据迁移：Room 2→3（建新表，无数据搬迁）

## UI/UX 变更声明

```yaml
ui_impact: true
design_system_mode: generated
design_system_fallback_reason: ""
pages: []
```

## 复用测试 ID
- UT-S09-01 — 心语 record 落轻事件路径不变（提炼为附加动作，不干扰记录）
- UT-S02-02 — 模型降级时提炼静默跳过（同一 degraded 语义）
