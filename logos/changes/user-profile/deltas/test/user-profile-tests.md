# delta — test/user-profile（Android 单机增量）

## ADDED — 用户画像测试（user-profile 增量）

### A.3 画像提炼与存取

| 编号 | 描述 | 前置条件 | 操作 | 预期 |
|------|------|---------|------|------|
| AND-PR-01 | 对话后提炼：明说偏好 → declared | 模型返回 source=declared | extractAndStorePreferences | preferences 新增一行 |
| AND-PR-02 | 推断偏好 → inferred | 模型返回 source=inferred | 同上 | source=inferred 落库 |
| AND-PR-03 | 同 key+value 去重 | 已有相同条目 | 再次提炼相同内容 | 不重复插入（计数不变） |
| AND-PR-04 | 一次最多 2 条 | 模型返回 3 条 | extractAndStorePreferences | 只存前 2 条 |
| AND-PR-05 | 模型降级静默跳过 | 模型未配置/失败 | extractAndStorePreferences | 返回 0，不报错（对齐 UT-S02-02 降级语义） |
| AND-PR-06 | ask 注入画像 | 有画像条目 | 问建议 | 上下文含画像区块；冲突选项按画像排序（如减肥→自助靠后） |
| AND-PR-07 | 画像可删除 | 任一条目 | deletePreference | 条目消失 |
| AND-PR-08 | Room 2→3 迁移 | v2 库 | 升级 | preferences 表建成、旧数据保留 |

（实现验证：编译+单测回归通过、模拟器启动无崩溃、preferences 表建成 user_version=3；提炼 E2E 依赖真实模型对话）
