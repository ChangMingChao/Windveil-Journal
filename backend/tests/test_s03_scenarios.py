"""S03 场景测试（端到端 HTTP）。

覆盖 ST-S03-01~12、15。时钟通过 /api/test/clock 注入，调度通过
/api/test/scheduler/tick 手动触发，断言经 /api/test/outbox 与
/api/test/latest-email 两个后门读取——与编排 core-S03-timing.json 一致。
ST-S03-13/14 为 [manual]（光晕动效、真机 Web Push），不产出 JSONL。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

UNDERSTANDING = {
    "understanding": {
        "kind": "future_wish",
        "feeling": "喘口气",
        "conditions": {"title": "学会滑雪"},
        "smallest_step": "先看一段入门视频",
    },
    "question": "想在哪座山？",
}


class FakeLLM:
    async def understand_wish(self, text: str):  # noqa: ANN201, ARG002
        from app.agent import UnderstandResult

        return UnderstandResult.model_validate(UNDERSTANDING)


class FlakyPush:
    """可控推送替身：ok 记账成功；gone 抛异常模拟 410（EX-16.1）。"""

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.sent: list[str] = []

    async def send(self, *, endpoint: str, p256dh: str, auth: str, body: str) -> None:
        del p256dh, auth, body
        if self.mode == "gone":
            raise RuntimeError("SubscriptionGone")
        self.sent.append(endpoint)


@pytest.fixture
async def env(app_env: None, tmp_path) -> AsyncIterator[tuple]:  # noqa: ANN001
    import os

    os.environ["APP_BASE_URL"] = "http://t"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "objects")

    from app.agent import set_llm_provider
    from app.clock import clock
    from app.config import get_settings
    from app.db import dispose_engines
    from app.main import create_app
    from app.notify import InMemoryEmailSender, set_senders
    from app.storage import set_storage

    get_settings.cache_clear()
    set_storage(None)
    set_llm_provider(FakeLLM())
    push, email = FlakyPush(), InMemoryEmailSender()
    set_senders(push, email)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post("/api/test/clock", json={"now": "2026-09-01T12:00:00+08:00"})
        yield client, push, email
    clock.set_fixed(None)
    set_llm_provider(None)
    set_senders(None, None)
    set_storage(None)
    await dispose_engines()


async def _signup(client: AsyncClient, *, with_push: bool = True) -> tuple[dict, str]:
    r = await client.post("/api/v1/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 201
    body = r.json()
    h = {"Authorization": f"Bearer {body['access_token']}"}
    uid = body["user"]["id"]
    if with_push:
        assert (
            await client.post("/api/test/push-subscription", json={"user_id": uid})
        ).status_code == 204
    return h, uid


def _fresh(uid: str) -> dict:
    """时钟被推到很远之后重新签一个 access token。

    真实用户走 /auth/refresh，编排里为了聚焦 S03 的行为直接重签。
    """
    import uuid as _uuid

    from app.security import issue_access_token

    return {"Authorization": f"Bearer {issue_access_token(_uuid.UUID(uid))}"}


async def _seed(client: AsyncClient, h: dict, text: str) -> str:
    r = await client.post("/api/v1/wishes", headers=h, json={"source": "text", "text": text})
    assert r.status_code == 201, r.text
    return r.json()["wish"]["id"]


@pytest.mark.asyncio
async def test_ST_S03_01_season_timing_delivers_once(env) -> None:  # noqa: ANN001
    client, push, _ = env
    h, uid = await _signup(client)
    wid = await _seed(client, h, "想在冬天学会滑雪")

    r = await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "season", "season": "winter"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "brewing"
    assert body["timing"]["trigger_kind"] == "time"
    assert "入冬" in body["timing"]["label"]
    assert body["timing"]["next_trigger_at"] is not None

    await client.post("/api/test/clock", json={"now": "2026-12-08T09:00:00+08:00"})
    tick = await client.post("/api/test/scheduler/tick")
    assert tick.status_code == 200
    stats = tick.json()
    assert stats["scanned"] >= 1 and stats["enqueued"] == 1 and stats["delivered"] == 1

    box = await client.get(f"/api/test/outbox?user_id={uid}")
    assert box.status_code == 200
    data = box.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["kind"] == "timing" and item["status"] == "delivered"
    assert item["channel"] == "push"
    assert "九月" in item["body"] and "滑雪" in item["body"]
    assert data["delivered_count_this_week"] == 1
    assert len(push.sent) == 1

    ready = await client.post(f"/api/v1/wishes/{wid}/ready", headers=_fresh(uid))
    assert ready.status_code == 200
    assert ready.json()["state"] == "wind"


@pytest.mark.asyncio
async def test_ST_S03_02_after_months_timing(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h, _ = await _signup(client)
    wid = await _seed(client, h, "想重新开始画画")
    r = await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 3}
    )
    assert r.status_code == 200
    assert r.json()["state"] == "brewing"
    assert r.json()["timing"]["next_trigger_at"][:7] in ("2026-11", "2026-12")
    # 幂等
    again = await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 3}
    )
    assert again.status_code == 200


@pytest.mark.asyncio
async def test_ST_S03_03_signal_timing_triggered_by_fatigue(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h, uid = await _signup(client)
    wid = await _seed(client, h, "想一个人去海边待两天")
    r = await client.put(f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "when_tired"})
    assert r.status_code == 200
    assert r.json()["timing"]["trigger_kind"] == "signal"
    assert r.json()["timing"]["next_trigger_at"] is None

    first = await client.post("/api/test/scheduler/tick")
    assert first.json()["enqueued"] == 0

    # 对话链路检出疲惫信号后回写触发时间（EX-11.1）
    from app.db import session_scope
    from app.services import trigger_fatigue_signals

    async with session_scope(__import__("uuid").UUID(uid)) as s:
        assert await trigger_fatigue_signals(s, __import__("uuid").UUID(uid)) == 1

    second = await client.post("/api/test/scheduler/tick")
    assert second.json()["enqueued"] == 1


@pytest.mark.asyncio
async def test_ST_S03_04_none_never_enters_scheduler(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h, uid = await _signup(client)
    wid = await _seed(client, h, "想给未来的自己写一封信")
    r = await client.put(f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "none"})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "seeded"
    assert body["timing"]["trigger_kind"] == "none"
    assert body["timing"]["next_trigger_at"] is None
    assert "你说你会自己想起它" in body["timing"]["label"]

    await client.post("/api/test/clock", json={"now": "2027-09-01T12:00:00+08:00"})
    tick = await client.post("/api/test/scheduler/tick")
    assert tick.json()["enqueued"] == 0
    assert (await client.get(f"/api/test/outbox?user_id={uid}")).json()["items"] == []


@pytest.mark.asyncio
async def test_ST_S03_05_invalid_timing_leaves_state_untouched(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h, _ = await _signup(client)
    wid = await _seed(client, h, "想去看一次日落")
    base = await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "season", "season": "autumn"}
    )
    baseline = base.json()["timing"]["next_trigger_at"]

    for bad in (
        {"type": "season"},
        {"type": "month_day", "month_day": "2027-02-30"},
        {"type": "after_months", "after_months": 2},
        {"type": "weather"},
    ):
        r = await client.put(f"/api/v1/wishes/{wid}/timing", headers=h, json=bad)
        assert r.status_code == 422, bad
        assert r.json()["code"] == "TIMING_INVALID"

    after = await client.get(f"/api/v1/wishes/{wid}", headers=h)
    assert after.json()["timing"]["next_trigger_at"] == baseline
    assert after.json()["state"] == "brewing"


@pytest.mark.asyncio
async def test_ST_S03_06_lock_contention_is_silent(env) -> None:  # noqa: ANN001
    from pathlib import Path

    from app.config import get_settings
    from app.scheduler import FileLock

    client, _, _ = env
    holder = FileLock(Path(get_settings().LOCAL_STORAGE_DIR).parent / ".scheduler.lock")
    assert holder.acquire() is True
    try:
        tick = await client.post("/api/test/scheduler/tick")
        assert tick.status_code == 200
        assert tick.json() == {
            "scanned": 0, "enqueued": 0, "deferred": 0, "delivered": 0, "failed": 0
        }
    finally:
        holder.release()


@pytest.mark.asyncio
async def test_ST_S03_07_weekly_budget_caps_at_three(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h, uid = await _signup(client)
    ids = [await _seed(client, h, f"预算测试愿望 {i}") for i in range(5)]
    for wid in ids:
        r = await client.put(
            f"/api/v1/wishes/{wid}/timing",
            headers=h,
            json={"type": "after_months", "after_months": 1},
        )
        assert r.status_code == 200

    await client.post("/api/test/clock", json={"now": "2026-10-02T09:00:00+08:00"})
    tick = (await client.post("/api/test/scheduler/tick")).json()
    assert tick["delivered"] == 3

    box = (await client.get(f"/api/test/outbox?user_id={uid}")).json()
    assert box["delivered_count_this_week"] == 3
    delivered = [i for i in box["items"] if i["status"] == "delivered"]
    deferred = [i for i in box["items"] if i["status"] == "deferred_to_next_week"]
    assert len(delivered) == 3
    assert len(deferred) == 2
    # 不产生合并式提醒：每条都只讲一件事
    assert all("待处理" not in i["body"] for i in box["items"])

    listed = (await client.get("/api/v1/wishes", headers=_fresh(uid))).json()
    assert sum(1 for i in listed["items"] if i["soft_deferred"]) == 2


@pytest.mark.asyncio
async def test_ST_S03_08_duplicate_scan_is_idempotent(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h, uid = await _signup(client)
    wid = await _seed(client, h, "想去看海")
    await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 1}
    )
    await client.post("/api/test/clock", json={"now": "2026-10-02T09:00:00+08:00"})
    first = (await client.post("/api/test/scheduler/tick")).json()
    assert first["enqueued"] == 1 and first["delivered"] == 1

    second = (await client.post("/api/test/scheduler/tick")).json()
    assert second["enqueued"] == 0 and second["delivered"] == 0

    box = (await client.get(f"/api/test/outbox?user_id={uid}")).json()
    assert len(box["items"]) == 1
    assert box["delivered_count_this_week"] == 1


@pytest.mark.asyncio
async def test_ST_S03_09_push_gone_falls_back_to_email(env) -> None:  # noqa: ANN001
    client, push, _ = env
    push.mode = "gone"
    h, uid = await _signup(client)
    link = await client.post(
        "/api/v1/auth/link-email",
        headers=h,
        json={"email": "fallback@example.com", "password": "Passw0rd!"},
    )
    assert link.status_code == 200
    wid = await _seed(client, h, "想去一次长途徒步")
    await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 1}
    )
    await client.post("/api/test/clock", json={"now": "2026-10-02T09:00:00+08:00"})
    tick = (await client.post("/api/test/scheduler/tick")).json()
    assert tick["delivered"] == 1

    box = (await client.get(f"/api/test/outbox?user_id={uid}")).json()
    assert box["items"][0]["channel"] == "email"
    assert len(push.sent) == 0  # 一次时机只送 1 条，不双发

    mail = await client.get("/api/test/latest-email?to=fallback@example.com")
    assert mail.status_code == 200
    assert "长途徒步" in mail.json()["body"]
    assert "逾期" not in mail.json()["body"] and "任务" not in mail.json()["body"]


@pytest.mark.asyncio
async def test_ST_S03_10_both_channels_fail_keeps_budget(env) -> None:  # noqa: ANN001
    client, push, _ = env
    push.mode = "gone"
    h, uid = await _signup(client)  # 匿名用户无邮箱 → 两条通道都不可用
    wid = await _seed(client, h, "想学一门乐器")
    await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 1}
    )
    await client.post("/api/test/clock", json={"now": "2026-10-02T09:00:00+08:00"})
    for _ in range(4):
        await client.post("/api/test/clock", json={"now": "2026-10-05T09:00:00+08:00"})
        await client.post("/api/test/scheduler/tick")

    box = (await client.get(f"/api/test/outbox?user_id={uid}")).json()
    assert box["items"][0]["status"] in ("pending", "failed")
    assert box["items"][0]["attempts"] >= 1
    assert box["delivered_count_this_week"] == 0


@pytest.mark.asyncio
async def test_ST_S03_11_defer_has_no_counter(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h, _ = await _signup(client)
    wid = await _seed(client, h, "想去看海")
    await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 1}
    )
    r = await client.post(f"/api/v1/wishes/{wid}/defer", headers=h, json={})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "brewing"
    assert body["soft_deferred"] is False
    assert "defer_count" not in body and "overdue_days" not in body


@pytest.mark.asyncio
async def test_ST_S03_12_oldest_timing_set_at_wins(env) -> None:  # noqa: ANN001
    """周预算只剩 1 条时，投递的是用户最早定下的那件事（Step 11 排序键）。

    注意全部动作必须落在同一个自然周内（2026-10-05 周一起），
    否则跨周会重置预算，测不到顺延分支。
    """
    client, _, _ = env
    h, uid = await _signup(client)

    # 用两条把本周额度消耗到只剩 1 条
    await client.post("/api/test/clock", json={"now": "2026-10-05T08:00:00+08:00"})
    for i in range(2):
        wid = await _seed(client, _fresh(uid), f"占额度 {i}")
        r = await client.put(
            f"/api/v1/wishes/{wid}/timing",
            headers=_fresh(uid),
            json={"type": "month_day", "month_day": "2026-10-05"},
        )
        assert r.status_code == 200, r.text
    await client.post("/api/test/clock", json={"now": "2026-10-05T10:00:00+08:00"})
    assert (await client.post("/api/test/scheduler/tick")).json()["delivered"] == 2

    # 三张卡的 timing_set_at 分别是「半年前 / 一个月前 / 昨天」，到期日同为 10-07
    await client.post("/api/test/clock", json={"now": "2026-04-02T09:00:00+08:00"})
    oldest = await _seed(client, _fresh(uid), "半年前就定下的那件事")
    assert (
        await client.put(
            f"/api/v1/wishes/{oldest}/timing",
            headers=_fresh(uid),
            json={"type": "month_day", "month_day": "2026-10-07"},
        )
    ).status_code == 200

    await client.post("/api/test/clock", json={"now": "2026-09-02T09:00:00+08:00"})
    mid = await _seed(client, _fresh(uid), "一个月前设的")
    await client.put(
        f"/api/v1/wishes/{mid}/timing",
        headers=_fresh(uid),
        json={"type": "month_day", "month_day": "2026-10-07"},
    )

    await client.post("/api/test/clock", json={"now": "2026-10-06T09:00:00+08:00"})
    newest = await _seed(client, _fresh(uid), "昨天随手设的")
    await client.put(
        f"/api/v1/wishes/{newest}/timing",
        headers=_fresh(uid),
        json={"type": "month_day", "month_day": "2026-10-07"},
    )

    # 同一周内的 10-07 到期：只剩 1 条额度
    await client.post("/api/test/clock", json={"now": "2026-10-07T09:00:00+08:00"})
    tick = (await client.post("/api/test/scheduler/tick")).json()
    assert tick["delivered"] == 1
    assert tick["deferred"] == 2

    box = (await client.get(f"/api/test/outbox?user_id={uid}")).json()
    delivered = [i for i in box["items"] if i["status"] == "delivered"]
    assert delivered[-1]["wish_id"] == oldest


@pytest.mark.asyncio
async def test_ST_S03_15_email_fallback_when_no_subscription(env) -> None:  # noqa: ANN001
    """从未注册 push 订阅的账号直接走邮件兜底（与 410 同一代码路径）。"""
    client, push, _ = env
    h, uid = await _signup(client, with_push=False)
    await client.post(
        "/api/v1/auth/link-email",
        headers=h,
        json={"email": "nopush@example.com", "password": "Passw0rd!"},
    )
    wid = await _seed(client, h, "想去一次长途徒步")
    await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 1}
    )
    await client.post("/api/test/clock", json={"now": "2026-10-02T09:00:00+08:00"})
    assert (await client.post("/api/test/scheduler/tick")).json()["delivered"] == 1

    box = (await client.get(f"/api/test/outbox?user_id={uid}")).json()
    assert box["items"][0]["channel"] == "email"
    assert push.sent == []
    mail = await client.get("/api/test/latest-email?to=nopush@example.com")
    assert "长途徒步" in mail.json()["body"]
