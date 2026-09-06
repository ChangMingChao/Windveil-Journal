"""heart-voice-holiday-timing 迁移：wishes.timing_type 枚举增 holiday。

原表 CHECK 为匿名内联约束（0001_batch1_core），SQLite 无法单独修改 CHECK，
需整表重建。坑位（0008 同款）：SQLite 的 ALTER TABLE RENAME 会把所有子表
外键 REFERENCES 级联改写到新表名。因此顺序必须是：
  1) 用原 DDL（CHECK 换新）建 wishes__rebuild；
  2) wishes 改名为 wishes__old（子表外键随之指向 wishes__old）；
  3) 逐个重建引用 wishes__old 的子表，把外键改写回 wishes；
  4) 拷数据、删旧表、wishes__rebuild 改名就位。
"""

revision = "0010_holiday_timing"
down_revision = "0009_lightweight_events"
branch_labels = None
depends_on = None

_OLD = "('season','month_day','after_months','free_weekend','when_tired','none')"
_NEW = "('season','month_day','after_months','free_weekend','when_tired','none','holiday')"


def _table_sql(bind, name: str) -> str:
    return bind.exec_driver_sql(
        "select sql from sqlite_master where type='table' and name=?", (name,)
    ).fetchone()[0]


def _rebuild(new_check: str, old_check: str) -> None:
    from alembic import op

    bind = op.get_bind()

    ddl = _table_sql(bind, "wishes")
    compact = ddl.replace("\n", "").replace(" ", "")
    if new_check.replace(" ", "") in compact:
        return  # 已是目标形态（幂等）
    if old_check.replace(" ", "") not in compact:
        raise RuntimeError("wishes.timing_type CHECK 与预期不符，迁移中止")

    # 原始 DDL 的 CHECK 折行不确定，用正则跨行替换整段 CHECK
    import re

    pattern = re.compile(
        r"timing_type TEXT CHECK \(timing_type IS NULL OR timing_type IN\s*"
        + re.escape(old_check).replace("\\'", "'") + r"\)"
    )
    if not pattern.search(ddl):
        raise RuntimeError("wishes.timing_type CHECK 正则未命中，迁移中止")
    new_ddl = pattern.sub(
        "timing_type TEXT CHECK (timing_type IS NULL OR timing_type IN " + new_check + ")",
        ddl,
        count=1,
    )
    tmp = "wishes__rebuild"
    bind.exec_driver_sql(f'DROP TABLE IF EXISTS "{tmp}"')
    # DDL 表名可能带或不带引号（CREATE TABLE "wishes" / CREATE TABLE wishes）
    if "CREATE TABLE \"wishes\"" in new_ddl:
        new_ddl = new_ddl.replace('CREATE TABLE "wishes"', f'CREATE TABLE "{tmp}"', 1)
    else:
        new_ddl = new_ddl.replace("CREATE TABLE wishes", f'CREATE TABLE "{tmp}"', 1)
    bind.exec_driver_sql(new_ddl)

    # 1) 拷数据到新表（此时 wishes 还在，直接 INSERT ... SELECT）
    cols = ", ".join('"' + r[1] + '"' for r in bind.exec_driver_sql('PRAGMA table_info("wishes")').fetchall())
    bind.exec_driver_sql(f'INSERT INTO "{tmp}" ({cols}) SELECT {cols} FROM "wishes"')

    # 2) 旧表改名（子表外键级联指向 wishes__old）
    bind.exec_driver_sql("PRAGMA foreign_keys = OFF")
    bind.exec_driver_sql('ALTER TABLE "wishes" RENAME TO "wishes__old"')

    # 3) 修复子表外键：重建每张引用 wishes__old 的表，改回 wishes
    children = [
        r[0]
        for r in bind.exec_driver_sql(
            "select name from sqlite_master where type='table' and sql like '%wishes__old%'"
        ).fetchall()
    ]
    for t in children:
        cddl = _table_sql(bind, t)
        ttmp = t + "__rb"
        bind.exec_driver_sql(f'DROP TABLE IF EXISTS "{ttmp}"')
        ci = cddl.index("(")
        bind.exec_driver_sql(
            f'CREATE TABLE "{ttmp}" ' + cddl[ci:].replace("wishes__old", "wishes")
        )
        ccols = ", ".join('"' + r[1] + '"' for r in bind.exec_driver_sql(f'PRAGMA table_info("{t}")').fetchall())
        bind.exec_driver_sql(f'INSERT INTO "{ttmp}" ({ccols}) SELECT {ccols} FROM "{t}"')
        bind.exec_driver_sql(f'DROP TABLE "{t}"')
        bind.exec_driver_sql(f'ALTER TABLE "{ttmp}" RENAME TO "{t}"')

    # 4) 新表就位
    bind.exec_driver_sql('DROP TABLE "wishes__old"')
    bind.exec_driver_sql(f'ALTER TABLE "{tmp}" RENAME TO "wishes"')
    bind.exec_driver_sql("PRAGMA foreign_keys = ON")


def upgrade() -> None:
    from alembic import op

    _rebuild(_NEW, _OLD)


def downgrade() -> None:
    from alembic import op

    bind = op.get_bind()
    bind.exec_driver_sql("UPDATE wishes SET timing_type = NULL WHERE timing_type = 'holiday'")
    _rebuild(_OLD, _NEW)
