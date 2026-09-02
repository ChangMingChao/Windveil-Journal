"""Clock 抽象。

架构第七节把系统时钟列为外部依赖，测试策略为 fixed-value：
时机到达、60 天停滞、发生日期早于种下日期这些断言都必须能注入固定时间。
业务代码一律用 now()，禁止直接调用 datetime.now()。
"""

from __future__ import annotations

from datetime import UTC, datetime


class Clock:
    def __init__(self) -> None:
        self._fixed: datetime | None = None

    def now(self) -> datetime:
        return self._fixed if self._fixed is not None else datetime.now(UTC)

    def set_fixed(self, value: datetime | None) -> None:
        """置 None 恢复真实时钟（system.yaml → testSetClock）。

        注入值统一归一到 UTC。不归一的话，同一个时间点会有两种线上表现形式：
        刚写入的对象带注入时的偏移（`2026-10-19T12:00:00+08:00`），
        从库里读回来的经 TZDateTime 转换后是 `2026-10-19T04:00:00Z`——
        同一个字段在「刚创建」与「再取一次」两种响应里长得不一样。
        """
        if value is not None and value.tzinfo is None:
            raise ValueError("fixed time must be timezone-aware")
        self._fixed = value.astimezone(UTC) if value is not None else None


clock = Clock()
