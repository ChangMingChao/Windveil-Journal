"""时机计算。

S03 Step 5 的硬约束：`next_trigger_at` 必须由服务端按 users.timezone 计算，
禁止前端传入——否则用户设备的时区或时钟错误会直接变成提醒时间错误。

6 种时机类型里只有 4 种由时间触发；`when_tired` 是信号类（EX-11.1），
`none` 永不提醒（EX-4.1）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.clock import clock

SEASON_START_MONTH = {"spring": 3, "summer": 6, "autumn": 9, "winter": 12}
ALLOWED_AFTER_MONTHS = (1, 3, 6, 12)
REMIND_HOUR = 9  # 本地时间上午 9 点，不在深夜打扰人
_MONTH_DAY_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


class TimingError(ValueError):
    """时机参数非法（EX-4.2）。"""


@dataclass(frozen=True)
class TimingPlan:
    timing_type: str
    timing_value: str | None
    trigger_kind: str
    next_trigger_at: datetime | None
    occurrence: str | None


def _local_at(tz: ZoneInfo, day: date, hour: int = REMIND_HOUR) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=tz).astimezone(UTC)


def _add_months(day: date, months: int) -> date:
    total = day.month - 1 + months
    year, month = day.year + total // 12, total % 12 + 1
    # 逐日回退处理「1 月 31 日 + 1 月」这类不存在的日期
    for candidate in range(day.day, 0, -1):
        try:
            return date(year, month, candidate)
        except ValueError:
            continue
    raise TimingError("cannot shift date")  # pragma: no cover


def plan_timing(
    *, timing_type: str, timezone: str, season: str | None = None,
    month_day: str | None = None, after_months: int | None = None,
    holidays: list[str] | None = None,
) -> TimingPlan:
    tz = ZoneInfo(timezone)
    now_local = clock.now().astimezone(tz)
    today = now_local.date()

    if timing_type == "none":
        return TimingPlan("none", None, "none", None, None)

    if timing_type == "when_tired":
        # 不是时间条件：Scheduler 的扫描集合天然排除它（EX-11.1）
        return TimingPlan("when_tired", None, "signal", None, None)

    if timing_type == "season":
        if season not in SEASON_START_MONTH:
            raise TimingError("season must be one of spring/summer/autumn/winter")
        month = SEASON_START_MONTH[season]
        year = today.year if (month, 1) > (today.month, today.day) else today.year + 1
        when = _local_at(tz, date(year, month, 1))
        return TimingPlan("season", season, "time", when, f"season:{season}:{year}")

    if timing_type == "month_day":
        if not month_day:
            raise TimingError("month_day is required")
        # 与 wishes.yaml 的 pattern ^\d{4}-\d{2}(-\d{2})?$ 严格一致：必须补零
        if not _MONTH_DAY_RE.match(month_day):
            raise TimingError("month_day format must be YYYY-MM or YYYY-MM-DD")
        parts = month_day.split("-")
        try:
            if len(parts) == 2:
                target = date(int(parts[0]), int(parts[1]), 1)
            else:
                target = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError as exc:  # 2027-02-30 这类不存在的日期
            raise TimingError("month_day is not a real date") from exc
        if target < today:
            raise TimingError("month_day is in the past")
        when = _local_at(tz, target)
        return TimingPlan("month_day", month_day, "time", when, f"month_day:{month_day}")

    if timing_type == "after_months":
        if after_months not in ALLOWED_AFTER_MONTHS:
            raise TimingError("after_months must be one of 1/3/6/12")
        target = _add_months(today, after_months)
        when = _local_at(tz, target)
        return TimingPlan(
            "after_months", str(after_months), "time", when, f"after_months:{target.isoformat()}"
        )

    if timing_type == "holiday":
        # 「法定节假日」（heart-voice-holiday-timing）：用户从内置数据枚举中
        # 多选节假日名，服务端取最近到来的一个匹配日计算触发时刻。
        # 数据缺年份或所选名称无匹配 → TIMING_INVALID（显式选择不可瞎猜）。
        from app.holidays import next_holiday_occurrence

        wanted = [h for h in (holidays or []) if h]
        if not wanted:
            raise TimingError("holidays is required")
        found = next_holiday_occurrence(wanted, today)
        if found is None:
            raise TimingError("no upcoming holiday matched in holiday data")
        target, name = found
        when = _local_at(tz, target)
        return TimingPlan("holiday", name, "time", when, f"holiday:{name}:{target.isoformat()}")

    if timing_type == "free_weekend":
        # 「空闲周末」= 下一个非调休的周末日（holiday-aware-timing）：
        # 从明天起顺延扫描，命中第一个「周六或周日 且 不在当年调休上班日中」的日期。
        # 数据缺年份时 workdays 恒为空 → 第一个周末命中，即退化为现状语义（EX-P.6）。
        # 触发时刻沿用既有的本地上午约定；上限 45 天防死循环（数据最密也不会扫满）。
        from app.holidays import is_workday

        target = None
        for offset in range(1, 46):
            day = today + timedelta(days=offset)
            if day.weekday() >= 5 and not is_workday(day):
                target = day
                break
        if target is None:  # pragma: no cover —— 45 天内必有周末，防御性兜底
            target = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
        when = _local_at(tz, target)
        return TimingPlan(
            "free_weekend", None, "time", when, f"free_weekend:{target.isoformat()}"
        )

    raise TimingError(f"unknown timing type: {timing_type}")


def week_start(moment: datetime, timezone: str) -> date:
    """自然周起始日：用户时区的周一（S03 Step 13）。

    用 UTC 的周一会让东八区的周一凌晨被算进上一周，导致周预算错位。
    """
    local = moment.astimezone(ZoneInfo(timezone))
    return (local - timedelta(days=local.weekday())).date()


def signal_occurrence(moment: datetime) -> str:
    """信号类时机在触发时才生成 occurrence，按天去重。"""
    return f"signal:{moment.astimezone(UTC).date().isoformat()}"
