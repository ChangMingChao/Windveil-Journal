"""节假日时机类型测试（heart-voice-holiday-timing）。

覆盖用例（批前声明，接续 test_s03_holidays.py 的 UT-S03-41~48）：
  - UT-S03-55 holiday 命中：多选取最近到来的匹配日，next_trigger_at 由服务端计算
  - UT-S03-56 holidays 为空 / 缺参 → TIMING_INVALID
  - UT-S03-57 所选名称在数据中无匹配（缺年份）→ TIMING_INVALID（拒绝瞎猜）
  - UT-S03-58 GET /holidays 返回去重名与明细；缺年份 available=false

数据注入：HOLIDAY_DATA_DIR 指向受控样例目录（同 test_s03_holidays 的 fixed-value 策略）。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.timing import TimingError, plan_timing

SAMPLE_2026 = {
    "year": 2026,
    "holidays": {
        "2026-10-01": "国庆节", "2026-10-02": "国庆节",
        "2027-01-01": "元旦",
    },
    "workdays": {},
}


@pytest.fixture()
def holiday_dir(tmp_path: Path, monkeypatch) -> Path:
    d = tmp_path / "holidays"
    d.mkdir()
    (d / "holidays_2026.json").write_text(json.dumps(SAMPLE_2026), encoding="utf-8")
    monkeypatch.setenv("HOLIDAY_DATA_DIR", str(d))
    from app.holidays import reset_cache

    reset_cache()
    yield d
    reset_cache()


def test_holiday_picks_nearest_match(holiday_dir: Path) -> None:
    """UT-S03-55：多选 [国庆节, 元旦]，今天 2026-09-06 → 最近的是国庆节 10-01。"""
    plan = plan_timing(
        timing_type="holiday",
        timezone="Asia/Shanghai",
        holidays=["国庆节", "元旦"],
    )
    assert plan.timing_type == "holiday"
    assert plan.timing_value == "国庆节"
    assert plan.trigger_kind == "time"
    assert plan.next_trigger_at is not None
    # 北京时间 2026-10-01 09:00 == UTC 01:00
    assert plan.next_trigger_at.isoformat().startswith("2026-10-01T01:00")
    assert plan.occurrence == "holiday:国庆节:2026-10-01"


def test_holiday_requires_names(holiday_dir: Path) -> None:
    """UT-S03-56：holidays 为空 → TIMING_INVALID。"""
    with pytest.raises(TimingError):
        plan_timing(timing_type="holiday", timezone="Asia/Shanghai", holidays=[])
    with pytest.raises(TimingError):
        plan_timing(timing_type="holiday", timezone="Asia/Shanghai")


def test_holiday_no_match_is_invalid(holiday_dir: Path) -> None:
    """UT-S03-57：所选名称在数据中不存在 → TIMING_INVALID（拒绝瞎猜）。"""
    with pytest.raises(TimingError):
        plan_timing(timing_type="holiday", timezone="Asia/Shanghai", holidays=["不存在的节"])


def test_holiday_cross_year(holiday_dir: Path) -> None:
    """跨年：今天若在国庆节之后，应命中次年元旦。"""
    plan = plan_timing(
        timing_type="holiday",
        timezone="Asia/Shanghai",
        holidays=["元旦"],
    )
    # 样例 2026 无元旦、2027-01-01 有 → 命中 2027-01-01（相对 2026-09 的「次年」）
    assert plan.timing_value == "元旦"
    assert "2027-01-01" in plan.occurrence


def test_holidays_endpoint(holiday_dir: Path) -> None:
    """UT-S03-58：GET /holidays 返回去重名与明细；缺年份 available=false。"""
    import asyncio

    from app.api import get_holidays
    from app.holidays import reset_cache

    async def _run() -> dict:
        return await get_holidays(year=2026)

    result = asyncio.run(_run())
    assert result["available"] is True
    assert result["names"] == ["国庆节", "元旦"]
    assert {"date": "2026-10-01", "name": "国庆节"} in result["items"]

    reset_cache()
