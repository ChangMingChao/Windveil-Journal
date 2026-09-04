"""pytest 配置 + OpenLogos reporter。

Reporter 契约见 logos/spec/test-results.md：
  - 输出 logos/resources/verify/test-results.jsonl
  - 每行 {"id","status","duration_ms","timestamp"[,"error"]}
  - 首次运行 truncate，之后 append
  - 用例 ID 从测试函数名提取（UT_S01_01 → UT-S01-01）

数据库改为 SQLite 后不再需要任何外部服务：每个测试用临时文件库，
装载 logos/resources/database/schema.sql 的 Batch 1 子集（即 0001 迁移的 DDL）。
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest

_ID_RE = re.compile(r"(UT|ST)_S\d{2}_\d{2,3}")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "logos" / "logos.config.json").exists():
            return parent
    return here.parents[2]


REPO_ROOT = _repo_root()
RESULT_PATH = REPO_ROOT / "logos" / "resources" / "verify" / "test-results.jsonl"
SCHEMA_PATH = REPO_ROOT / "logos" / "resources" / "database" / "schema.sql"
_initialized = False


def _ensure_file() -> None:
    global _initialized
    if not _initialized:
        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text("", encoding="utf-8")
        _initialized = True


def _extract_id(nodeid: str) -> str | None:
    m = _ID_RE.search(nodeid)
    return m.group().replace("_", "-") if m else None


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):  # noqa: ANN001, ANN201
    outcome = yield
    report = outcome.get_result()
    if report.when not in ("call", "setup"):
        return
    if report.when == "setup" and not report.skipped:
        return
    test_id = _extract_id(item.nodeid)
    if not test_id:
        return
    _ensure_file()
    if report.skipped:
        status = "skip"
    elif report.passed:
        status = "pass"
    else:
        status = "fail"
    record: dict[str, object] = {
        "id": test_id,
        "status": status,
        "duration_ms": round(report.duration * 1000),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scenario": test_id.split("-")[1],
    }
    if status == "fail":
        record["error"] = str(report.longrepr)[:500]
    with RESULT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- 数据库夹具

_DDL_CACHE: str | None = None
MIGRATIONS = (
    "0001_batch1_core.py",
    "0002_batch3_reminders.py",
    "0003_batch4_steps.py",
    "0004_batch5_orphans.py",
    "0005_batch6_memories.py",
    "0006_batch7_scheduler_heartbeat.py",
    "0007_s07_recall.py",
    "0008_preferences_availability_timing.py",
)


def batch1_ddl() -> str:
    """按顺序拼接各批迁移的 DDL，等价于 alembic upgrade head。"""
    global _DDL_CACHE
    if _DDL_CACHE is None:
        import importlib.util

        parts = []
        for name in MIGRATIONS:
            mig = REPO_ROOT / "backend" / "migrations" / "versions" / name
            spec = importlib.util.spec_from_file_location(name.replace(".py", ""), mig)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            parts.append(mod.DDL)
            if hasattr(mod, "DDL_WISHES"):
                parts.append(mod.DDL_WISHES)
        _DDL_CACHE = chr(10).join(parts)
    return _DDL_CACHE


@pytest.fixture
def sqlite_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def raw_db(sqlite_path: Path):  # noqa: ANN201
    """一个已建好 Batch 1 表结构的同步 sqlite3 连接（用于 DB 约束单测）。"""
    import sqlite3

    con = sqlite3.connect(sqlite_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(batch1_ddl())
    con.commit()
    try:
        yield con
    finally:
        con.close()


@pytest.fixture
def app_env(sqlite_path: Path):  # noqa: ANN201
    """把应用指向临时 SQLite 库，并清掉配置缓存。"""
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{sqlite_path.as_posix()}"
    os.environ["APP_ENV"] = "test"
    os.environ["ENCRYPTION_KEY"] = "test-encryption-key"

    from app.config import get_settings

    get_settings.cache_clear()
    import sqlite3

    con = sqlite3.connect(sqlite_path)
    exists = con.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()[0]
    if not exists:  # raw_db 夹具可能已建过表，避免重复执行 DDL
        con.executescript(batch1_ddl())
        con.commit()
    con.close()
    yield
    get_settings.cache_clear()
