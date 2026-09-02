"""S03 单元测试（不依赖数据库的部分）。

时机计算、周起始、退避序列、文案模板都是纯函数，因此可以脱离数据库覆盖边界。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.clock import clock
from app.config import get_settings
from app.notify import render_reminder
from app.timing import ALLOWED_AFTER_MONTHS, TimingError, plan_timing, week_start

SH = "Asia/Shanghai"


@pytest.fixture(autouse=True)
def fixed_clock():  # noqa: ANN201
    clock.set_fixed(datetime(2026, 9, 1, 12, 0, tzinfo=ZoneInfo(SH)))
    yield
    clock.set_fixed(None)


def test_UT_S03_01_type_is_required() -> None:
    with pytest.raises(TimingError):
        plan_timing(timing_type="", timezone=SH)


def test_UT_S03_02_type_enum_enforced() -> None:
    with pytest.raises(TimingError):
        plan_timing(timing_type="weather", timezone=SH)


def test_UT_S03_03_season_requires_value() -> None:
    with pytest.raises(TimingError):
        plan_timing(timing_type="season", timezone=SH)


def test_UT_S03_04_season_must_be_one_of_four() -> None:
    with pytest.raises(TimingError):
        plan_timing(timing_type="season", timezone=SH, season="rainy")
    assert plan_timing(timing_type="season", timezone=SH, season="winter").trigger_kind == "time"


def test_UT_S03_05_month_day_format() -> None:
    with pytest.raises(TimingError):
        plan_timing(timing_type="month_day", timezone=SH, month_day="2027-3")
    assert plan_timing(timing_type="month_day", timezone=SH, month_day="2027-03").timing_value == "2027-03"
    assert plan_timing(timing_type="month_day", timezone=SH, month_day="2027-03-15").timing_value == "2027-03-15"


def test_UT_S03_06_month_day_must_be_real_date() -> None:
    with pytest.raises(TimingError):
        plan_timing(timing_type="month_day", timezone=SH, month_day="2027-02-30")


def test_UT_S03_07_after_months_enum() -> None:
    assert ALLOWED_AFTER_MONTHS == (1, 3, 6, 12)
    with pytest.raises(TimingError):
        plan_timing(timing_type="after_months", timezone=SH, after_months=2)
    for ok in ALLOWED_AFTER_MONTHS:
        assert plan_timing(timing_type="after_months", timezone=SH, after_months=ok).next_trigger_at


def test_UT_S03_08_defer_defaults_to_three_months() -> None:
    plan = plan_timing(timing_type="after_months", timezone=SH, after_months=3)
    assert plan.next_trigger_at is not None
    delta = plan.next_trigger_at - clock.now()
    assert timedelta(days=88) < delta < timedelta(days=93)


def test_UT_S03_09_client_supplied_trigger_time_is_ignored() -> None:
    """plan_timing 的签名里没有 next_trigger_at —— 前端根本没有传入的入口。"""
    import inspect

    assert "next_trigger_at" not in inspect.signature(plan_timing).parameters


def test_UT_S03_10_timing_is_idempotent() -> None:
    a = plan_timing(timing_type="season", timezone=SH, season="winter")
    b = plan_timing(timing_type="season", timezone=SH, season="winter")
    assert a == b
    assert a.occurrence == "season:winter:2026"


def test_UT_S03_19_season_computed_in_user_timezone() -> None:
    plan = plan_timing(timing_type="season", timezone=SH, season="winter")
    assert plan.next_trigger_at is not None
    local = plan.next_trigger_at.astimezone(ZoneInfo(SH))
    assert (local.month, local.day, local.hour) == (12, 1, 9)


def test_UT_S03_20_when_tired_is_signal_without_time() -> None:
    plan = plan_timing(timing_type="when_tired", timezone=SH)
    assert plan.trigger_kind == "signal"
    assert plan.next_trigger_at is None


def test_UT_S03_21_none_keeps_no_trigger() -> None:
    plan = plan_timing(timing_type="none", timezone=SH)
    assert plan.trigger_kind == "none"
    assert plan.next_trigger_at is None


def test_UT_S03_22_week_start_is_local_monday() -> None:
    # 2026-09-01 是周二；东八区周一应为 08-31
    assert week_start(clock.now(), SH).isoformat() == "2026-08-31"
    # 东八区周一 00:30 若按 UTC 计算会落到上一周，这里必须仍是本周
    monday_early = datetime(2026, 8, 31, 0, 30, tzinfo=ZoneInfo(SH))
    assert week_start(monday_early, SH).isoformat() == "2026-08-31"
    assert week_start(monday_early.astimezone(UTC), SH).isoformat() == "2026-08-31"


def test_UT_S03_23_defer_order_key_is_timing_set_at() -> None:
    """顺延排序键是「用户何时定下时机」，不是「时机何时到」。"""
    import inspect

    from app import scheduler

    src = inspect.getsource(scheduler.run_tick)
    assert "order_by(Wish.timing_set_at)" in src
    assert "order_by(Wish.next_trigger_at)" not in src


def test_UT_S03_25_backoff_sequence() -> None:
    s = get_settings()
    assert s.REMINDER_BACKOFF_SECONDS == (300, 1800, 7200)
    assert s.REMINDER_MAX_ATTEMPTS == 3


def test_UT_S03_26_reminder_body_is_template_only() -> None:
    body = render_reminder(
        seeded_at=datetime(2026, 9, 12, tzinfo=UTC),
        original_text="想在冬天学会滑雪",
        timing_label="正在等待合适的风：入冬",
    )
    assert body == "你在九月说过想在冬天学会滑雪，正在等待合适的风：入冬了。"
    assert "逾期" not in body and "任务" not in body
    # 超长原话按 40 字截断，仍是逐字引用
    long_body = render_reminder(
        seeded_at=datetime(2026, 1, 1, tzinfo=UTC), original_text="海" * 60, timing_label="入冬"
    )
    assert "海" * 40 in long_body
    assert "海" * 41 not in long_body


def test_UT_S03_28_no_defer_count_column_exists() -> None:
    """库中不存在顺延次数 / 逾期天数一类列，UI 在结构上无法显示它们。"""
    from app.models import Wish

    columns = {c.name for c in Wish.__table__.columns}
    for forbidden in ("defer_count", "overdue_days", "completion_rate", "streak_days"):
        assert forbidden not in columns
    assert "soft_deferred" in columns  # 只有布尔标记，没有次数
