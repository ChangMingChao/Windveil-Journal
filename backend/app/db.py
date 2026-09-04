"""数据库连接与数据隔离守卫。

SQLite 没有行级安全，schema.sql 文末因此定义了两道应用层防线：
  第一道 —— 仓储层统一注入 owner_id（services.py）
  第二道 —— 本文件的 owner_guard：对 owner 表的读写若未带 owner_id 绑定参数
            直接抛异常，而不是返回错误数据

诚实记录：守卫是进程内断言，绕过 ORM 直接开 sqlite3 连接即可绕过它；
RLS 是数据库强制的。这是选择 SQLite 必然付出的代价（架构 5.3）。
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

# 与 schema.sql 文末「受守卫保护的表」列表一致
OWNED_TABLES = frozenset(
    {
        "users",
        "sessions",
        "onboarding_answers",
        "media",
        "wishes",
        "wish_amendments",
        "wish_steps",
        "wish_messages",
        "wish_photos",
        "memories",
        "memory_photos",
        "push_subscriptions",
        "reminder_outbox",
        "reminder_weekly_counters",
        "pending_agent_jobs",
        "user_preferences",
        "availability_windows",
        "timing_proposals",
    }
)

# 关联表不冗余 owner_id，按父表主键限定即视为已限定
# （等价于原 PostgreSQL 方案里 wish_photos / memory_photos 的 EXISTS 策略）
ASSOC_TABLES = {"wish_photos": "wish_id", "memory_photos": "memory_id"}

_GUARDED_VERBS = re.compile(r"^\s*(SELECT|UPDATE|DELETE)\b", re.IGNORECASE)
_TABLE_RE = re.compile(r"\b(?:FROM|UPDATE|JOIN)\s+\"?(\w+)\"?", re.IGNORECASE)


class OwnerGuardError(RuntimeError):
    """未按 owner 维度约束的查询。属于编程错误，不应被捕获后继续。"""


def _statement_is_scoped(sql: str, tables: set[str]) -> bool:
    """粗粒度断言：语句是否被限定在单个 owner 的数据上。

    这不是完备的 SQL 分析，而是一道能在测试与开发期抓住「忘了加 owner_id」
    的护栏。真正的强隔离在 PostgreSQL + RLS 方案里，见架构 5.3 的取舍说明。
    """
    lowered = sql.lower()
    if "owner_id" in lowered:
        return True
    # 主键等值查询（session.get 生成的形态）
    if re.search(r"\bwhere\b[^;]*\.id\s*=", lowered) or re.search(
        r"\bwhere\b[^;]*\bid\b\s*=", lowered
    ):
        return True
    # 仅涉及关联表时，按父表主键限定即可
    assoc_only = tables and tables <= set(ASSOC_TABLES)
    if assoc_only:
        return any(f"{ASSOC_TABLES[t]} =" in lowered.replace("  ", " ") for t in tables)
    return False


_engine: AsyncEngine | None = None
_bypass: ContextVar[bool] = ContextVar("owner_guard_bypass", default=False)


@contextmanager
def owner_guard_bypass() -> Iterator[None]:
    """显式声明一次跨 owner 查询。

    只有认证链路需要它：按邮箱查用户（登录、绑定查重）本质上无法带 owner_id。
    每处使用都必须是有意的，因此写成显式上下文而不是全局开关。
    """
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


def install_owner_guard(engine: AsyncEngine) -> None:
    sync_engine: Engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _guard(  # noqa: ANN202
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        del conn, cursor, parameters, context, executemany
        if _bypass.get():
            return
        if not _GUARDED_VERBS.match(statement):
            return
        tables = {t.lower() for t in _TABLE_RE.findall(statement)}
        if not (tables & OWNED_TABLES):
            return
        if _statement_is_scoped(statement, tables & OWNED_TABLES):
            return
        raise OwnerGuardError(
            "对 owner 表的查询必须限定 owner_id 或主键：" + " ".join(statement.split())[:200]
        )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().DATABASE_URL, future=True)

        @event.listens_for(_engine.sync_engine, "connect")
        def _pragmas(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            # schema.sql 头部要求：外键默认关闭、WAL 更适合读写并发、忙等避免瞬时 locked
            cur.execute("PRAGMA foreign_keys = ON")
            cur.execute("PRAGMA journal_mode = WAL")
            cur.execute("PRAGMA busy_timeout = 5000")
            cur.close()

        install_owner_guard(_engine)
        # SMOKE-core-08 / 部署方案 §7-7：启动日志里要能确认守卫真的装上了
        logging.getLogger("app.db").info("owner_guard installed")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope(
    owner_id: UUID | None = None, role: str = "app"
) -> AsyncIterator[AsyncSession]:
    """打开一个事务作用域。

    role 与 owner_id 参数保留但在 SQLite 下不再驱动数据库层行为（无角色、无 RLS）；
    保留签名是为了让调用方代码在将来换回 PostgreSQL 时不必改动。
    """
    from app.faults import check_fault

    check_fault("db")  # 故障注入点：模拟数据库不可用（ST-S01-03）
    del role, owner_id
    maker = get_sessionmaker()
    async with maker() as session:
        async with session.begin():
            yield session


async def apply_schema(schema_sql: str) -> None:
    """按 schema.sql 建库（测试与本地开发用；生产走 Alembic）。"""
    engine = get_engine()
    raw = await engine.raw_connection()
    try:
        await raw.driver_connection.executescript(schema_sql)
        await raw.driver_connection.commit()
    finally:
        raw.close()


async def dispose_engines() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
