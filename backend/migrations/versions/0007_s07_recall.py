"""S07 迁移：记录愿望进入安静放下区的时间。"""

from alembic import op
from sqlalchemy import Column, Text

revision = "0007_s07_recall"
down_revision = "0006_batch7_scheduler_heartbeat"
branch_labels = None
depends_on = None

DDL = ""


def upgrade() -> None:
    bind = op.get_bind()
    columns = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(wishes)")}
    table_sql = bind.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'wishes'"
    ).scalar_one()
    has_constraint = "wishes_let_go_timestamp_matches_state" in (table_sql or "")
    if "let_go_at" not in columns or not has_constraint:
        with op.batch_alter_table("wishes", recreate="always") as batch_op:
            if "let_go_at" not in columns:
                batch_op.add_column(Column("let_go_at", Text(), nullable=True))
            if not has_constraint:
                batch_op.create_check_constraint(
                    "wishes_let_go_timestamp_matches_state",
                    "state = 'let_go' OR let_go_at IS NULL",
                )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_wishes_owner_let_go_at "
        "ON wishes(owner_id, let_go_at DESC, seeded_at DESC, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wishes_owner_let_go_at")