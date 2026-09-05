"""S03 节假日感知测试（holiday-aware-timing）。

覆盖用例（批前声明，接续 test_s03_*.py 的 UT-S03-01~40 / ST-S03-01~21）：
  - UT-S03-41 ~ UT-S03-48（8 个）
  - ST-S03-22 / ST-S03-23（2 个，编排 delta 同名 flow 的执行实现）

数据注入：`HOLIDAY_DATA_DIR` 指向 tmp 下的受控样例目录（架构第七节 fixed-value 策略）；
2026 含国庆长假（10/1–10/8）与调休上班日（10/10 周六），2027 无文件（EX-P.6 降级路径）。
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from test_s03_proposals import BASE, ProposalLLM, VALID_DRAFT, _fresh, _subscribe
from test_s05_scenarios import T0

TZ = timezone(timedelta(hours=8))
SAMPLE_2026 = {
    "year": 2026,
    "source": "测试样例（正式数据以官方公告为准）",
    "updated_at": "2026-09-05",
    "holidays": {
        "2026-10-01": "国庆节", "2026-10-02": "国庆节", "2026-10-03": "国庆节",
        "2026-10-04": "国庆节", "2026-10-05": "国庆节", "2026-10-06": "国庆节",
        "2026-10-07": "国庆节", "2026-10-08": "国庆节",
    },
    "workdays": {"2026-10-10": "周末调休上班"},
}


def _write_data(dir_: Path, year: int, payload: dict | None) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    target = dir_ / f"holidays_{year}.json"
    if payload is not None:
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return dir_


@pytest.fixture
def holiday_dir(tmp_path: Path) -> Path:
    return _write_data(tmp_path, 2026, SAMPLE_2026)  # 2027 故意缺文件


@pytest.fixture
async def env(
    app_env: None, tmp_path: Path, holiday_dir: Path
) -> AsyncIterator[tuple[AsyncClient, ProposalLLM]]:
    os.environ["APP_BASE_URL"] = "http://t"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "objects")
    os.environ["HOLIDAY_DATA_DIR"] = str(holiday_dir)

    from app.agent import set_llm_provider
    from app.clock import clock
    from app.config import get_settings
    from app.db import dispose_engines
    from app.holidays import reset_cache
    from app.main import create_app
    from app.notify import DisabledPushSender, InMemoryEmailSender, set_senders
    from app.storage import set_storage

    llm = ProposalLLM()
    get_settings.cache_clear()
    reset_cache()
    set_storage(None)
    set_llm_provider(llm)
    set_senders(DisabledPushSender(), InMemoryEmailSender())
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post("/api/test/clock", json={"now": T0.isoformat()})
        yield client, llm
    clock.set_fixed(None)
    set_llm_provider(None)
    set_senders(None, None)
    set_storage(None)
    reset_cache()
    os.environ.pop("HOLIDAY_DATA_DIR", None)
    await dispose_engines()


async def _at(client: AsyncClient, moment: datetime) -> None:
    r = await client.post("/api/test/clock", json={"now": moment.isoformat()})
    assert r.status_code == 204


async def _signup(client: AsyncClient) -> tuple[dict, str]:
    r = await client.post(f"{BASE}/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 201
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


# ---------------------------------------------------------------- UT


def test_UT_S03_41_loader_lazy_cache_and_schema_tolerance(holiday_dir: Path, tmp_path: Path) -> None:
    """加载器：合法文件按 schema 读取；缺字段文件按空集；按年份缓存。"""
    from app import holidays

    os.environ["HOLIDAY_DATA_DIR"] = str(holiday_dir)
    holidays.reset_cache()
    try:
        data = holidays.load_year(2026)
        assert data["holidays"]["2026-10-01"] == "国庆节"
        assert data["workdays"]["2026-10-10"] == "周末调休上班"
        assert holidays.load_year(2026) is data, "同一年份命中进程内缓存"

        # 缺字段文件 → 空集，不抛错
        broken = _write_data(tmp_path, 2029, {"year": 2029, "holidays": "not-a-dict"})
        os.environ["HOLIDAY_DATA_DIR"] = str(broken.parent)
        holidays.reset_cache()
        assert holidays.load_year(2029) == holidays.empty()
    finally:
        holidays.reset_cache()
        os.environ.pop("HOLIDAY_DATA_DIR", None)


def test_UT_S03_42_tuned_workday_saturday_skipped(holiday_dir: Path) -> None:
    """调休上班的周六不算「空闲周末」：10/10（周六）在 workdays → 跳到 10/11（周日）。"""
    from datetime import date

    from app import holidays
    from app.timing import plan_timing

    os.environ["HOLIDAY_DATA_DIR"] = str(holiday_dir)
    holidays.reset_cache()
    try:
        from app.clock import clock

        clock.set_fixed(datetime(2026, 10, 9, 12, 0, tzinfo=TZ))  # 周五
        plan = plan_timing(timing_type="free_weekend", timezone="Asia/Shanghai")
        assert plan.next_trigger_at is not None
        local = plan.next_trigger_at.astimezone(TZ)
        assert local.date() == date(2026, 10, 11), f"跳过调休周六 10/10，命中周日：{local.date()}"
        assert local.hour == 9, "触发时刻沿用既有的本地上午约定"
    finally:
        clock.set_fixed(None)
        holidays.reset_cache()
        os.environ.pop("HOLIDAY_DATA_DIR", None)


def test_UT_S03_43_first_free_weekend_after_long_holiday(holiday_dir: Path) -> None:
    """长周末之后：10/12（周一）起的下一个非调休周末是 10/17（周六）。"""
    from datetime import date

    from app import holidays
    from app.clock import clock
    from app.timing import plan_timing

    os.environ["HOLIDAY_DATA_DIR"] = str(holiday_dir)
    holidays.reset_cache()
    try:
        clock.set_fixed(datetime(2026, 10, 12, 12, 0, tzinfo=TZ))
        plan = plan_timing(timing_type="free_weekend", timezone="Asia/Shanghai")
        local = plan.next_trigger_at.astimezone(TZ)
        assert local.date() == date(2026, 10, 17)
    finally:
        clock.set_fixed(None)
        holidays.reset_cache()
        os.environ.pop("HOLIDAY_DATA_DIR", None)


def test_UT_S03_44_missing_year_degrades_safely(holiday_dir: Path) -> None:
    """缺 2027 数据：退化为「下一个周六」的现状语义，不报错（EX-P.6）。"""
    from datetime import date

    from app import holidays
    from app.clock import clock
    from app.timing import plan_timing

    os.environ["HOLIDAY_DATA_DIR"] = str(holiday_dir)
    holidays.reset_cache()
    try:
        clock.set_fixed(datetime(2027, 3, 2, 12, 0, tzinfo=TZ))  # 周二
        plan = plan_timing(timing_type="free_weekend", timezone="Asia/Shanghai")
        local = plan.next_trigger_at.astimezone(TZ)
        assert local.date() == date(2027, 3, 6), "无数据即第一个周六"
        assert holidays.load_year(2027)["holidays"] == {}
    finally:
        clock.set_fixed(None)
        holidays.reset_cache()
        os.environ.pop("HOLIDAY_DATA_DIR", None)


def test_UT_S03_45_other_timing_types_unaffected(holiday_dir: Path) -> None:
    """season/month_day/after_months 的计算不受节假日影响（语义未变的边界确认）。"""
    from app import holidays
    from app.clock import clock
    from app.timing import plan_timing

    os.environ["HOLIDAY_DATA_DIR"] = str(holiday_dir)
    holidays.reset_cache()
    try:
        clock.set_fixed(datetime(2026, 10, 9, 12, 0, tzinfo=TZ))
        p1 = plan_timing(timing_type="season", timezone="Asia/Shanghai", season="winter")
        assert p1.next_trigger_at.astimezone(TZ).date().isoformat() == "2026-12-01"
        p2 = plan_timing(timing_type="month_day", timezone="Asia/Shanghai", month_day="2027-02-14")
        assert p2.next_trigger_at.astimezone(TZ).date().isoformat() == "2027-02-14"
        p3 = plan_timing(timing_type="after_months", timezone="Asia/Shanghai", after_months=1)
        assert p3.next_trigger_at.astimezone(TZ).date().isoformat() == "2026-11-09"
    finally:
        clock.set_fixed(None)
        holidays.reset_cache()
        os.environ.pop("HOLIDAY_DATA_DIR", None)


def test_UT_S03_46_upcoming_facts_feed_context(holiday_dir: Path) -> None:
    """节假日事实文案行：日期区间 + 名称（提议上下文的节假日来源）。"""
    from datetime import date

    from app import holidays

    os.environ["HOLIDAY_DATA_DIR"] = str(holiday_dir)
    holidays.reset_cache()
    try:
        facts = holidays.upcoming_facts(date(2026, 9, 20))
        assert any("国庆节" in f and "2026-10-01" in f and "2026-10-08" in f for f in facts)
        # 缺年份：无事实行
        assert holidays.upcoming_facts(date(2027, 3, 2)) == []
    finally:
        holidays.reset_cache()
        os.environ.pop("HOLIDAY_DATA_DIR", None)


async def test_UT_S03_47_proposal_evidence_carries_calendar(env) -> None:
    """有数据年份：生成的建议 evidence 含 calendar 条目，id 为文件标识（非 UUID）。"""
    client, llm = env
    _at_clock = datetime(2026, 9, 20, 12, 0, tzinfo=TZ)  # 长假前：建议可引用临近的国庆
    await _at(client, _at_clock)
    h, _ = await _signup(client)  # 在新时钟下签发，token 不会中途过期
    llm.draft = {
        "timing_type": "free_weekend",
        "timing_value": None,
        "reason": "因为 10/1–10/8 是国庆长假，之后第一个周末更从容",
        "confidence": 85,
    }
    r = await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "想去看海"})
    wid = r.json()["wish"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    cal = [e for e in p["evidence"] if e["kind"] == "calendar"]
    assert cal and cal[0]["id"] == "holidays-2026", p["evidence"]


def test_UT_S03_48_data_file_is_traceable(holiday_dir: Path) -> None:
    """数据文件含 source 与 updated_at（可追溯）；缺失字段按空集处理。"""
    from app import holidays

    os.environ["HOLIDAY_DATA_DIR"] = str(holiday_dir)
    holidays.reset_cache()
    try:
        data = holidays.load_year(2026)
        assert data["source"] and data["updated_at"]
        assert data["year"] == 2026
    finally:
        holidays.reset_cache()
        os.environ.pop("HOLIDAY_DATA_DIR", None)


# ---------------------------------------------------------------- ST


async def test_ST_S03_22_manual_free_weekend_hits_real_rest_day(env) -> None:
    """手动设置 free_weekend 命中真实休息日：跳过调休周六 10/10，命中 10/11。"""
    client, llm = env
    await _at(client, datetime(2026, 10, 9, 12, 0, tzinfo=TZ))
    h, _ = await _signup(client)  # 新时钟下签发
    r = await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "想去看一次日出"})
    wid = r.json()["wish"]["id"]
    r = await client.put(f"{BASE}/wishes/{wid}/timing", headers=h, json={"type": "free_weekend"})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "brewing"
    local = datetime.fromisoformat(r.json()["timing"]["next_trigger_at"]).astimezone(TZ)
    assert local.date().isoformat() == "2026-10-11", r.json()["timing"]
    assert local.date().isoweekday() in (6, 7)


async def test_ST_S03_23_proposal_cites_holiday_and_chain_unchanged(env) -> None:
    """建议理由引用节假日：evidence 含 calendar；确认后提醒链路与节假日无关。"""
    client, llm = env
    await _at(client, datetime(2026, 9, 20, 12, 0, tzinfo=TZ))  # 长假前
    h, uid = await _signup(client)
    await _subscribe(client, uid)
    llm.draft = {
        "timing_type": "after_months",
        "timing_value": "1",
        "reason": "因为 10/1–10/8 是国庆长假，之后节奏会更松",
        "confidence": 82,
    }
    r = await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "想在冬天学会滑雪"})
    wid = r.json()["wish"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert any(e["kind"] == "calendar" and e["id"] == "holidays-2026" for e in p["evidence"])
    pid = p["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals/{pid}/confirm", headers=h)
    assert r.status_code == 200 and r.json()["wish"]["state"] == "brewing"
    # 时钟推进 → 调度 → outbox 1 条，文案仍为模板拼接（与节假日无关）
    await _at(client, datetime(2026, 11, 12, 12, 0, tzinfo=TZ))
    r = await client.post("/api/test/scheduler/tick")
    assert r.json()["delivered"] >= 1
    r = await client.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert len(r.json()["items"]) == 1 and "滑雪" in r.json()["items"][0]["body"]
