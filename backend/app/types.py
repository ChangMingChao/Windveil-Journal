"""SQLite 类型适配。

schema.sql 的类型约定（SQLite 无原生 UUID / 时间类型）：
  主键与外键 TEXT，存 UUID v4 字符串
  时间       TEXT，ISO 8601 UTC，形如 2026-09-01T12:00:00.000Z

这两个 TypeDecorator 让业务代码继续用 uuid.UUID 与 datetime，
落库形态则与 schema.sql 逐字一致。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, TypeDecorator

ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


class GUID(TypeDecorator[uuid.UUID]):
    """UUID ↔ TEXT(36)。"""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:  # noqa: ARG002
        if value is None:
            return None
        return str(value) if isinstance(value, uuid.UUID) else str(uuid.UUID(str(value)))

    def process_result_value(self, value: Any, dialect: Any) -> uuid.UUID | None:  # noqa: ARG002
        return None if value is None else uuid.UUID(value)


class TZDateTime(TypeDecorator[datetime]):
    """时区感知 datetime ↔ ISO 8601 UTC 字符串（带毫秒与 Z 后缀）。

    统一存 UTC：SQLite 的字符串比较等价于时间比较，只要格式固定且同为 UTC，
    索引与 WHERE next_trigger_at <= ? 都能正确工作。
    """

    impl = String(30)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:  # noqa: ARG002
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            raise ValueError("naive datetime is not allowed; use clock.now()")
        return value.astimezone(UTC).strftime(ISO_FMT)[:-4] + "Z"

    def process_result_value(self, value: Any, dialect: Any) -> datetime | None:  # noqa: ARG002
        if value is None:
            return None
        raw = value.replace("Z", "+00:00")
        # SQLite 的 DEFAULT strftime('%Y-%m-%dT%H:%M:%fZ') 产生三位毫秒，
        # Python 的 fromisoformat 从 3.11 起可直接解析
        return datetime.fromisoformat(raw).astimezone(UTC)
