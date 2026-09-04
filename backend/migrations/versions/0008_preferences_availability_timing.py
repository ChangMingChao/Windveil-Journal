"""preferences-availability-timing 迁移：新增 user_preferences / availability_windows / timing_proposals。

三张全新表，不改动既有表的任何列（部署方案「五·增补」：最安全的加表类迁移）。
DDL 与 logos/resources/database/schema.sql 逐字节一致（由脚本从 schema.sql 提取生成）。
"""

from alembic import op

revision = "0008_preferences_availability_timing"
down_revision = "0007_s07_recall"
branch_labels = None
depends_on = None

DDL = """
-- user_preferences（来源：auth.yaml → listPreferences, declarePreference,
--                   revokePreference, deletePreference；S08）
-- -----------------------------------------------------------------------------
CREATE TABLE user_preferences (
  -- @comment 偏好条目唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户。SQLite 无 RLS，隔离由仓储层注入 + 运行时守卫保证
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment entry 为单条偏好；digest 为 LLM 定期生成的「它的理解」摘要（S08 摘要支线 D1–D4）
  kind TEXT NOT NULL DEFAULT 'entry' CHECK (kind IN ('entry', 'digest')),
  -- @comment 主题键：entry 行为 relaxation/pace/companion/budget/other（与 P6 主题胶囊对应）；digest 行恒为 overall
  pref_key TEXT NOT NULL,
  -- @comment declared 为用户主动声明；inferred 为模型推断。用户写入一律 declared（服务端强制，S08 Step 8）
  source TEXT NOT NULL CHECK (source IN ('declared', 'inferred')),
  -- @comment 偏好内容，应用层 AES-256-GCM 加密。可查看、可删除；写接口响应不回显明文
  value_enc BLOB NOT NULL,
  -- @comment 0–100。declared 恒为 100（由 CHECK 强制）；inferred 由模型给出。UI 映射为置信档文案，不展示裸数字
  confidence INTEGER CHECK (confidence IS NOT NULL AND confidence BETWEEN 0 AND 100),
  -- @comment 撤回时间：仅 inferred 行可被用户撤回（「猜错了」）。非 NULL 即退出一切判断，保留审计痕迹
  revoked_at TEXT,
  -- @comment 创建时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 最后更新时间，由应用层刷新
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 用户声明不承认任何「不确定」：declared 行置信度必须为 100
  CONSTRAINT user_preferences_declared_is_certain
    CHECK (source = 'inferred' OR confidence = 100),
  -- @comment 摘要行不是撤回语义的对象（删除即可），与 entry 行共用 revoked_at 但 digest 恒为 NULL
  CONSTRAINT user_preferences_digest_never_revoked
    CHECK (kind = 'entry' OR revoked_at IS NULL)
);
-- @table-comment user_preferences 偏好记忆。区分「你说过的」与「我猜的」；
-- 撤回（软失效，保留痕迹）与删除（硬删除，无影子）是两个独立动作；
-- 摘要作为 kind='digest' 行与本表同生共死，同样可查看、可删除（S08）

-- 同一用户同一 kind+key 只有一行：声明是 UPSERT（最新为准），摘要只保留最近一份
CREATE UNIQUE INDEX idx_user_preferences_unique_key
  ON user_preferences(owner_id, kind, pref_key, source);
-- 「它记得我什么」列表：默认只取未撤回行（S08 Step 3）
CREATE INDEX idx_user_preferences_owner_active
  ON user_preferences(owner_id, kind, created_at) WHERE revoked_at IS NULL;
-- 摘要任务读取明细（S08 D1）
CREATE INDEX idx_user_preferences_digest_scan
  ON user_preferences(owner_id) WHERE kind = 'entry' AND revoked_at IS NULL;

-- availability_windows（来源：auth.yaml → listAvailability, createAvailabilityWindow,
--                       updateAvailabilityWindow, deleteAvailabilityWindow；S08）
-- -----------------------------------------------------------------------------
CREATE TABLE availability_windows (
  -- @comment 时段唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 周几，0=周一（ISO 8601），6=周日
  weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  -- @comment 开始分钟数（0 = 00:00）
  start_minute INTEGER NOT NULL CHECK (start_minute BETWEEN 0 AND 1439),
  -- @comment 结束分钟数（1440 = 当日 24:00）；必须晚于开始。跨午夜段由前端拆为两行
  end_minute INTEGER NOT NULL CHECK (end_minute BETWEEN 1 AND 1440),
  -- @comment 可选备注（如「带孩子出门前」），应用层加密。结构化字段（周几 + 分钟）明文存储：
  -- 它们只表达「一周里什么时候可能有空」，不含内容文本（架构 5.3 增补）
  note_enc BLOB,
  -- @comment 创建时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 最后更新时间
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CONSTRAINT availability_windows_ordered
    CHECK (end_minute > start_minute)
);
-- @table-comment availability_windows 用户声明的重复可用时段。是 free_weekend 类
-- 时机的 next_trigger_at 计算依据，也是「询问用户什么时候有空」克制原则的
-- 数据基础：有依据就不追问（S03 EX-P.2 / IA 5.3 第 7 条）

-- 周视图渲染与 free_weekend 计算：按用户取全部时段
CREATE INDEX idx_availability_windows_owner
  ON availability_windows(owner_id, weekday, start_minute);

-- timing_proposals（来源：wishes.yaml → createTimingProposal, listTimingProposals,
--                   confirmTimingProposal, rejectTimingProposal；S03 时机提议分支）
--
-- 四层边界（架构 5.4）：本表只承载第 1–3 层（提议、校验、决策）的痕迹。
-- Scheduler 永不读取本表；提醒只来自 wishes 的合法时机字段。
-- -----------------------------------------------------------------------------
CREATE TABLE timing_proposals (
  -- @comment 提议唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户，冗余存储供守卫层直接过滤
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 目标愿望，愿望删除时级联清除
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  -- @comment pending 待确认 / confirmed 已确认 / rejected 已拒绝 / expired 已过期
  --（含规则校验未通过与新提议替代两种来路）
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'confirmed', 'rejected', 'expired')),
  -- @comment 仅 4 种时间类：signal（when_tired）与 none 不是「可执行的时间」，不由模型提议
  timing_type TEXT NOT NULL
    CHECK (timing_type IN ('season', 'month_day', 'after_months', 'free_weekend')),
  -- @comment 参数：winter / 2027-03 或 2027-03-15 / 3 / NULL（free_weekend）
  timing_value TEXT,
  -- @comment 模型给出的参考展示值，仅供用户预览；永不写入 wishes——
  -- next_trigger_at 一律由服务端按 users.timezone 计算（与 S03 主路径同一原则）
  proposed_trigger_at TEXT,
  -- @comment 一句理由，应用层加密。文案须引用依据（IA 5.3 第 8 条「记忆可解释」）
  reason_enc BLOB,
  -- @comment 模型自报置信度 0–100；UI 映射为「大概猜的 / 比较确定」，不展示裸数字
  confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
  -- @comment 依据条目的 ID 引用数组（JSON 字符串，形如 [{"kind":"availability","id":"…"}]）。
  -- 只存 ID 不复制内容：条目被撤回/删除后引用自然失效（架构 5.3 增补），避免「删了还在用」
  evidence TEXT NOT NULL DEFAULT '[]',
  -- @comment 服务端规则校验结果（JSON 字符串，形如 {"valid":true,"reason_code":null}）。
  -- 校验失败的提议照常入库但立即 expired——保留「为什么这条建议没成立」的审计
  validation_result TEXT NOT NULL,
  -- @comment 用户确认或拒绝的时间；pending 与 expired 时为 NULL
  decided_at TEXT,
  -- @comment 建议有效期（默认创建后 7 天），由 Scheduler 低频扫描置 expired
  expires_at TEXT NOT NULL,
  -- @comment 创建时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 最后更新时间
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 确认/拒绝必须有决策时间，待确认/过期必须没有
  CONSTRAINT timing_proposals_decided_state_pairing
    CHECK ((status IN ('confirmed', 'rejected')) = (decided_at IS NOT NULL))
);
-- @table-comment timing_proposals LLM 时机建议。模型只到「提议待确认」为止：
-- confirm 是唯一能把建议变成 wishes 时机字段的通道，且请求体为空、
-- 不接受任何客户端时间字段（S03 EX-P.4）

-- 结构性保证「同一愿望至多 1 条待确认建议」：新提议产生前必须终结旧提议，
-- 与 wish_steps 的 idx_wish_steps_single_proposed 同一模式
CREATE UNIQUE INDEX idx_timing_proposals_single_pending
  ON timing_proposals(wish_id) WHERE status = 'pending';
-- 建议过期扫描（Scheduler 低频任务，S03 分支第 3 层）
CREATE INDEX idx_timing_proposals_expiry
  ON timing_proposals(expires_at) WHERE status = 'pending';
-- 详情页取当前 pending 与历史审计列表
CREATE INDEX idx_timing_proposals_wish_history
  ON timing_proposals(wish_id, created_at DESC);
"""


def upgrade() -> None:
    # 逐条执行，且必须走 exec_driver_sql 而非 op.execute：DDL 注释里含 JSON 示例
    # （{"valid":true,...}），text() 会把 ":true" 当绑定参数占位符而报错；
    # exec_driver_sql 原样下发给 sqlite3 驱动，不做参数解析。
    bind = op.get_bind()
    for stmt in [x.strip() for x in DDL.split(";\n") if x.strip()]:
        bind.exec_driver_sql(stmt)


def downgrade() -> None:
    op.exec_driver_sql(
        "DROP INDEX IF EXISTS idx_timing_proposals_wish_history; "
        "DROP INDEX IF EXISTS idx_timing_proposals_expiry; "
        "DROP INDEX IF EXISTS idx_timing_proposals_single_pending; "
        "DROP INDEX IF EXISTS idx_availability_windows_owner; "
        "DROP INDEX IF EXISTS idx_user_preferences_digest_scan; "
        "DROP INDEX IF EXISTS idx_user_preferences_owner_active; "
        "DROP INDEX IF EXISTS idx_user_preferences_unique_key; "
        "DROP TABLE IF EXISTS timing_proposals; "
        "DROP TABLE IF EXISTS availability_windows; "
        "DROP TABLE IF EXISTS user_preferences;"
    )
