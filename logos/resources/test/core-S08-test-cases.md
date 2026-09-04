## 一、单元测试用例

### 1.1 API 字段约束（来源：auth.yaml → declarePreference / createAvailabilityWindow 等）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S08-01 | pref_key 只接受 5 个主题键 | `declarePreference.pref_key.enum` | 已登录 | `{"pref_key":"weather","value":"…"}` | 422 `VALIDATION_FAILED` |
| UT-S08-02 | value 长度 1–200 | `declarePreference.value` | 已登录 | 空 / 201 字 | 422 `VALIDATION_FAILED` |
| UT-S08-03 | 请求中的 source/confidence 被忽略 | S08 Step 8 说明 | 已登录 | body 携带 `{"source":"inferred","confidence":1}` | 落库仍为 `declared` / `100` |
| UT-S08-04 | 写接口响应不回显 value 明文 | auth.yaml 敏感值不回显约定 | 已登录 | PUT 成功 | 响应含 id/pref_key/source 等元数据；无 `value` 字段 |
| UT-S08-05 | availability 时间区间必须有序 | `availability_windows_ordered CHECK`、EX-23.1 | 已登录 | `{weekday:5,start_minute:840,end_minute:780}` | 422 `AVAILABILITY_INVALID`；无半写入行 |
| UT-S08-06 | weekday 与分钟边界 | `weekday CHECK 0–6`、`start/end_minute CHECK` | 已登录 | `weekday=7`、`start_minute=1440`、`end_minute=0` | 均 422 `AVAILABILITY_INVALID` |
| UT-S08-07 | note 超长被拒 | `createAvailabilityWindow.note.maxLength: 50` | 已登录 | 51 字备注 | 422 `VALIDATION_FAILED` |
| UT-S08-08 | include_revoked 默认不返回撤回行 | `listPreferences.include_revoked` | 已撤回 1 条 | `GET /me/preferences` | 响应 items 不含该条；`include_revoked=true` 时返回且 `revoked_at` 非空 |

### 1.2 DB 约束（来源：schema.sql）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S08-09 | declared 行置信度必须为 100 | `user_preferences_declared_is_certain CHECK` | — | `source='declared', confidence=60` | 违反 CHECK |
| UT-S08-10 | digest 行不可撤回 | `user_preferences_digest_never_revoked CHECK` | — | `kind='digest', revoked_at=now()` | 违反 CHECK |
| UT-S08-11 | 同 owner 同 kind+key+source 唯一（不同 source 并存即「声明不覆盖推断」） | `idx_user_preferences_unique_key` | 已有 declared 行 | 同 key 同 source 再插一行 | 唯一冲突 → UPSERT 更新；inferred 行并存成功 |
| UT-S08-12 | 三张新表均在 owner_guard 保护清单 | schema.sql 守卫清单、S08 EX-19.1 | 用户 B 的 token | 读写用户 A 的偏好/时段/提议 | 全部 404；不暴露存在性 |
| UT-S08-13 | 偏好值与备注加密落库 | schema.sql `value_enc` / `note_enc` | 已声明偏好与时段 | 直查 `user_preferences.value_enc` / `availability_windows.note_enc` | BLOB 且不含明文子串 |
| UT-S08-14 | 时段跨午夜拆两行 | S08 Step 23 说明 | 已登录 | 22:30–次日 06:30 | 前端提交两行（`22:30–24:00` 与 `00:00–06:30`），均 201 |

### 1.3 业务规则（来源：时序图步骤说明）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S08-15 | 声明不覆盖推断（同 key 并存） | S08 Step 9 | 已有同 key inferred 行 | PUT 声明同 key | inferred 行原样保留；declared 行新建；判断时 declared 优先 |
| UT-S08-16 | revoke 仅对未撤回的 inferred 行生效 | EX-14.1 | declared 行 / 已撤回行 / 他人行 | POST revoke | 均 409 `PREFERENCE_NOT_REVOCABLE`；不产生第二条痕迹 |
| UT-S08-17 | 撤回与删除联动失效 pending 建议 | S08 Step 15 / Step 19、S03 EX-P.5 | pending 提议 evidence 引用该条目 | revoke 或 delete | 同事务把提议置 `expired`；confirm 后续返回 409 |
| UT-S08-18 | 删除为硬删除 | S08 Step 19、需求 S08 AC-04 | 已删除一条 | 直查表 + include_revoked=true | 行不存在；导出内容不含；无「已删除 N 条」计数 |
| UT-S08-19 | digest UPSERT 只保留最近一份 | S08 D4 | 已有 digest 行 | 摘要任务再次运行 | 同 key 行被更新而非新增；行数仍为 1 |
| UT-S08-20 | 摘要生成失败保持旧值且不重试 | EX-D2.1 | LLM mock 不可用；已有旧 digest | 运行摘要任务 | 旧 digest 行不变；无 pending 队列项；无 error 级日志 |

## 二、场景测试用例

### 2.1 主路径与异常

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S08-01 | 查看记忆：空→声明→读回 | Step 1→11 | 新账号 | GET（空）→ PUT 声明 → GET | 首次 GET 两列表均为空（EX-6.1 语义）；PUT 200 且响应无 value；再次 GET 返回 `source=declared`、`confidence=100`、value 明文与提交一致 |
| ST-S08-02 | 声明与推断并列不覆盖 | Step 7→11 | 预置同 key inferred 行（服务端注入） | PUT 声明同 key → GET | 两行并存：`inferred` 原样、`declared` 新增；无覆盖或合并 |
| ST-S08-03 | 撤回推断并联动失效建议 | Step 12→16、EX-14.1 | 预置 inferred 行 + 引用它的 pending 提议 | revoke → GET → confirm 提议 | revoke 200；默认列表消失、include_revoked 可见且 revoked_at 非空；提议转 expired；confirm 409；重复 revoke 409 |
| ST-S08-04 | 删除偏好不留影子 | Step 17→20、EX-19.1 | 已声明 1 条偏好 | DELETE → 直查 + GET | 204；重复 DELETE 404；表无该行；include_revoked 也不返回；无计数 |
| ST-S08-05 | 可用时段管理与非法输入 | Step 21→25、EX-23.1 | 已登录 | POST 合法时段 → POST end<=start → PATCH 修改 → DELETE | 合法 201；非法 422 且无写入；PATCH 200；DELETE 204、重复 404 |
| ST-S08-06 | 摘要支线：生成、覆盖与降级 | D1→D4、EX-D2.1 | 已有若干 entry 行 | 置 LLM mock ok → 触发摘要任务 → 置 mock 失败 → 再触发 | 首次生成 digest 行（加密）；再次触发 UPSERT 仍 1 行；失败轮 digest 不变、无重试队列、无 error 日志 |

### 2.2 人工验证用例（[manual]）

| ID | 描述 | 覆盖 Steps | 验证方式 |
|----|------|-----------|---------|
| ST-S08-07 [manual] | 来源徽标分层：「你说过的」（绿点）视觉强于「我猜的」（雾蓝空心点 + 置信档文案），不出现裸百分比 | Step 6 | 真实浏览器对照 `core-05` 原型 |
| ST-S08-08 [manual] | 空状态与撤回痕迹符合文案词典：空态为「它还什么都不知道。」；无任何条数统计、模型参数或技术字样 | Step 6 / EX-6.1 | 真实浏览器走查 |

## 三、覆盖度校验

- [x] 需求 S08 正常验收条件（2 条）：AC-01（声明并列）→ ST-S08-02、AC-02（撤回）→ ST-S08-03
- [x] 需求 S08 异常验收条件（2 条）：AC-03（提议不自动成提醒）→ ST-S03-16/17（见 S03 增量）、AC-04（删除无影子）→ ST-S08-04、UT-S08-18
- [x] EX 异常用例（6 个）：EX-6.1→ST-01、EX-14.1→ST-03/UT-16、EX-19.1→ST-04/UT-12、EX-23.1→ST-05/UT-05/06、EX-D2.1→ST-06/UT-20
- [x] DB CHECK / UNIQUE：declared_is_certain（UT-09）、digest_never_revoked（UT-10）、unique_key（UT-11）、availability_ordered（UT-05）、三表守卫（UT-12）
- [x] 隐私红线：value/note 加密（UT-13）、写响应不回显（UT-04）、硬删除无影子（UT-18）
- [x] Phase 2 交互级验收条件（4 条）：ST-S08-01/03/04/05；视觉 2 条 manual（07/08）

## 四、验收条件追溯

| AC ID | 验收条件（需求 S08） | 覆盖用例 |
|-------|---------------------|---------|
| S08-AC-01 | 正常：查看记忆并声明一条偏好（与猜测并列） | ST-S08-02, UT-S08-15, UT-S08-03 |
| S08-AC-02 | 正常：撤回一条模型推断 | ST-S08-03, UT-S08-16 |
| S08-AC-03 | 异常：模型提议未经确认不会变成任何提醒 | ST-S03-16, ST-S03-17, UT-S03-35/36/40（S03 增量文件） |
| S08-AC-04 | 异常：删除是彻底的，不留任何影子 | ST-S08-04, UT-S08-17/18, UT-S08-13 |
