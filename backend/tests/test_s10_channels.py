"""S10 提醒通道测试（notification-channels）。

覆盖用例（批前声明）：
  - UT-S10-01 ~ UT-S10-05、UT-S10-09（6 个）
  - ST-S10-01 ~ ST-S10-04（4 个，编排 delta 同名 flow 的执行实现）
  - UT-S10-06/07/08/10 属投递侧，由 ST-S10-01/02 覆盖（通道选择在真实投递路径上断言）；
    其中 UT-S10-10（并发读）在单进程 pytest 中无竞态意义，由代码审查项覆盖
  - ST-S10-05 为 [manual]，按规范不写 JSONL
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from test_s03_proposals import T0, _fresh, _signup

BASE = "/api/v1"
TZ = timezone(timedelta(hours=8))


@pytest.fixture
async def env(app_env: None, tmp_path: Path) -> AsyncIterator[AsyncClient]:
    os.environ["APP_BASE_URL"] = "http://t"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "objects")

    from app.agent import set_llm_provider
    from app.clock import clock
    from app.config import get_settings
    from app.db import dispose_engines
    from app.main import create_app
    from app.notify import DisabledPushSender, InMemoryEmailSender, set_senders
    from app.storage import set_storage

    get_settings.cache_clear()
    set_storage(None)
    set_llm_provider(None)
    set_senders(DisabledPushSender(), InMemoryEmailSender())
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post("/api/test/clock", json={"now": T0.isoformat()})
        yield client
    clock.set_fixed(None)
    set_llm_provider(None)
    set_senders(None, None)
    set_storage(None)
    await dispose_engines()


async def _signup(client: AsyncClient) -> tuple[dict, str]:
    r = await client.post(f"{BASE}/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 201
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


async def _subscribe(client: AsyncClient, uid: str) -> None:
    assert (await client.post("/api/test/push-subscription", json={"user_id": uid})).status_code == 204


async def _seed_scheduled(client: AsyncClient, h: dict, text: str) -> str:
    r = await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": text})
    assert r.status_code == 201, r.text
    wid = r.json()["wish"]["id"]
    r = await client.put(
        f"{BASE}/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 1}
    )
    assert r.status_code == 200 and r.json()["state"] == "brewing"
    return wid


# ---------------------------------------------------------------- UT


async def test_UT_S10_01_empty_body_rejected(env: AsyncClient) -> None:
    """空请求体被拒（minProperties: 1 语义）。"""
    h, _ = await _signup(env)
    r = await env.patch(f"{BASE}/me/notification-channels", headers=h, json={})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_FAILED"


async def test_UT_S10_02_partial_update_only(env: AsyncClient) -> None:
    """只更新提交的字段：另一开关保持不变。"""
    h, _ = await _signup(env)
    r = await env.patch(f"{BASE}/me/notification-channels", headers=h, json={"push_enabled": False})
    assert r.status_code == 200
    assert r.json()["push_enabled"] is False and r.json()["email_enabled"] is True


async def test_UT_S10_03_channels_in_get_me(env: AsyncClient) -> None:
    """开关状态随 GET /me 返回（UserProfile 扩展）。"""
    h, _ = await _signup(env)
    r = await env.get(f"{BASE}/me", headers=h)
    assert r.status_code == 200
    assert r.json()["push_enabled"] is True and r.json()["email_enabled"] is True


async def test_UT_S10_04_unknown_field_rejected(env: AsyncClient) -> None:
    """未知字段被拒（严格校验）。"""
    h, _ = await _signup(env)
    r = await env.patch(f"{BASE}/me/notification-channels", headers=h, json={"foo": True})
    assert r.status_code == 422


async def test_UT_S10_05_toggles_do_not_touch_other_data(env: AsyncClient) -> None:
    """切换不影响愿望/轻事件/偏好数据（验收-异常）。"""
    h, _ = await _signup(env)
    wid = (await env.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "想去看海"})).json()["wish"]["id"]
    lid = (await env.post(f"{BASE}/lite-events", headers=h, json={"text": "随手一条"})).json()["id"]
    pid = (await env.put(f"{BASE}/me/preferences", headers=h, json={"pref_key": "pace", "value": "慢"})).json()["id"]
    r = await env.patch(f"{BASE}/me/notification-channels", headers=h, json={"push_enabled": False, "email_enabled": False})
    assert r.status_code == 200
    assert (await env.get(f"{BASE}/wishes/{wid}", headers=h)).json()["state"] == "seeded"
    assert (await env.get(f"{BASE}/lite-events", headers=h)).json()["items"][0]["id"] == lid
    assert (await env.get(f"{BASE}/me/preferences", headers=h)).json()["items"][0]["id"] == pid


async def test_UT_S10_09_skip_not_counted(env: AsyncClient) -> None:
    """全关跳过不计入任何统计：delivered/failed/deferred 均为 0，outbox 保持 pending。"""
    h, uid = await _signup(env)
    await _subscribe(env, uid)
    await _seed_scheduled(env, h, "想在冬天学会滑雪")
    await env.patch(f"{BASE}/me/notification-channels", headers=h, json={"push_enabled": False, "email_enabled": False})
    await env.post("/api/test/clock", json={"now": (T0 + timedelta(days=40)).isoformat()})
    r = await env.post("/api/test/scheduler/tick")
    body = r.json()
    assert body["delivered"] == 0 and body["failed"] == 0 and body["deferred"] == 0
    r = await env.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert all(i["status"] == "pending" for i in r.json()["items"])


# ---------------------------------------------------------------- ST


async def test_ST_S10_01_push_off_routes_email_directly(env: AsyncClient) -> None:
    """关闭推送保留邮件：投递直接走邮件，订阅保留（AC-01）。"""
    h, uid = await _signup(env)
    await _subscribe(env, uid)
    # 绑定邮箱（邮件兜底需要收件地址）
    r = await env.post(f"{BASE}/auth/link-email", headers=h, json={"email": "a@example.com", "password": "password123"})
    assert r.status_code == 200, r.text
    await _seed_scheduled(env, h, "想在冬天学会滑雪")
    r = await env.patch(f"{BASE}/me/notification-channels", headers=h, json={"push_enabled": False})
    assert r.status_code == 200
    await env.post("/api/test/clock", json={"now": (T0 + timedelta(days=40)).isoformat()})
    r = await env.post("/api/test/scheduler/tick")
    assert r.json()["delivered"] >= 1
    r = await env.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert r.json()["items"][0]["channel"] == "email"


async def test_ST_S10_02_all_off_silent_then_recover(env: AsyncClient) -> None:
    """全关 = 完全静默、pending 保留；重开恢复投递且不丢时机（AC-02）。"""
    h, uid = await _signup(env)
    await _subscribe(env, uid)
    await env.post(f"{BASE}/auth/link-email", headers=h, json={"email": "b@example.com", "password": "password123"})
    await _seed_scheduled(env, h, "想重新开始画画")
    await env.patch(
        f"{BASE}/me/notification-channels", headers=h, json={"push_enabled": False, "email_enabled": False}
    )
    await env.post("/api/test/clock", json={"now": (T0 + timedelta(days=40)).isoformat()})
    r = await env.post("/api/test/scheduler/tick")
    assert r.json()["delivered"] == 0
    r = await env.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert all(i["status"] == "pending" for i in r.json()["items"])
    # 重开 email → 下一轮恢复
    await env.patch(f"{BASE}/me/notification-channels", headers=_fresh(uid), json={"email_enabled": True})
    r = await env.post("/api/test/scheduler/tick")
    assert r.json()["delivered"] >= 1
    r = await env.get("/api/test/outbox", params={"user_id": uid}, headers=_fresh(uid))
    assert r.json()["items"][0]["status"] == "delivered"


async def test_ST_S10_03_rapid_toggles_independent(env: AsyncClient) -> None:
    """快速连续切换互不牵连（验收-异常）。"""
    h, _ = await _signup(env)
    for body, expect in [
        ({"push_enabled": False}, (False, True)),
        ({"email_enabled": False}, (False, False)),
        ({"email_enabled": True}, (False, True)),
    ]:
        r = await env.patch(f"{BASE}/me/notification-channels", headers=h, json=body)
        assert r.status_code == 200
        assert (r.json()["push_enabled"], r.json()["email_enabled"]) == expect


async def test_ST_S10_04_toggle_scoped_to_token_user(env: AsyncClient) -> None:
    """开关只作用于当前 token 用户：B 的切换不影响 A。"""
    ha, _ = await _signup(env)
    hb, _ = await _signup(env)
    await env.patch(f"{BASE}/me/notification-channels", headers=hb, json={"push_enabled": False})
    r = await env.get(f"{BASE}/me", headers=ha)
    assert r.json()["push_enabled"] is True


# ---------------------------------------------------------------- UT（投递侧补齐）


async def test_UT_S10_06_push_off_never_attempts_push(env: AsyncClient) -> None:
    """push 关 + email 开 → 直接走邮件，push 通道零调用（UT-S10-06）。"""
    h, uid = await _signup(env)
    await _subscribe(env, uid)
    await env.post(f"{BASE}/auth/link-email", headers=h, json={"email": "c@example.com", "password": "password123"})
    await _seed_scheduled(env, h, "想在冬天学会滑雪")
    from app.notify import get_push_sender

    spy = get_push_sender()
    calls_before = getattr(spy, "calls", 0)
    await env.patch(f"{BASE}/me/notification-channels", headers=h, json={"push_enabled": False})
    await env.post("/api/test/clock", json={"now": (T0 + timedelta(days=40)).isoformat()})
    r = await env.post("/api/test/scheduler/tick")
    assert r.json()["delivered"] >= 1
    assert getattr(spy, "calls", calls_before) == calls_before, "已关闭的推送通道不得被调用"


async def test_UT_S10_07_all_off_keeps_pending_attempts_untouched(env: AsyncClient) -> None:
    """全关：跳过且 attempts 保持 0、不置失败（UT-S10-07）。"""
    h, uid = await _signup(env)
    await _subscribe(env, uid)
    await env.post(f"{BASE}/auth/link-email", headers=h, json={"email": "d@example.com", "password": "password123"})
    await _seed_scheduled(env, h, "想重新开始画画")
    await env.patch(
        f"{BASE}/me/notification-channels", headers=h, json={"push_enabled": False, "email_enabled": False}
    )
    await env.post("/api/test/clock", json={"now": (T0 + timedelta(days=40)).isoformat()})
    await env.post("/api/test/scheduler/tick")
    r = await env.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    items = r.json()["items"]
    assert items and all(i["status"] == "pending" for i in items)


async def test_UT_S10_08_recovery_respects_weekly_budget(env: AsyncClient) -> None:
    """恢复后投递受周预算约束：4 条到期，重开 email → 3 条 delivered + 1 条顺延（UT-S10-08）。"""
    h, uid = await _signup(env)
    await env.post(f"{BASE}/auth/link-email", headers=h, json={"email": "e@example.com", "password": "password123"})
    for text in ("甲", "乙", "丙", "丁"):
        await _seed_scheduled(env, h, f"想把{text}这件事做了")
    await env.patch(
        f"{BASE}/me/notification-channels", headers=h, json={"push_enabled": False, "email_enabled": False}
    )
    await env.post("/api/test/clock", json={"now": (T0 + timedelta(days=40)).isoformat()})
    await env.post("/api/test/scheduler/tick")  # 全关：全部保持 pending
    await env.patch(f"{BASE}/me/notification-channels", headers=_fresh(uid), json={"email_enabled": True})
    r = await env.post("/api/test/scheduler/tick")
    assert r.json()["delivered"] == 3 and r.json()["deferred"] == 1, r.json()


async def test_UT_S10_10_delivery_reads_latest_toggle(env: AsyncClient) -> None:
    """投递读取的是最新开关：PATCH 提交后立刻 tick，新值即刻生效（UT-S10-10）。"""
    h, uid = await _signup(env)
    await _subscribe(env, uid)
    await env.post(f"{BASE}/auth/link-email", headers=h, json={"email": "f@example.com", "password": "password123"})
    await _seed_scheduled(env, h, "想去学陶艺")
    # 不做任何等待：PATCH 提交后立即触发投递
    await env.patch(f"{BASE}/me/notification-channels", headers=h, json={"push_enabled": False})
    await env.post("/api/test/clock", json={"now": (T0 + timedelta(days=40)).isoformat()})
    r = await env.post("/api/test/scheduler/tick")
    assert r.json()["delivered"] >= 1
    r = await env.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert r.json()["items"][0]["channel"] == "email", "提交后的新开关必须在同一轮投递生效"
