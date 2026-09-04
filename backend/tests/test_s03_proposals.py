"""S03 时机提议分支测试（preferences-availability-timing）。

覆盖用例（批前声明，接续 test_s03_*.py 的 UT-S03-01~28 / ST-S03-01~15）：
  - UT-S03-29 ~ UT-S03-40（12 个）
  - ST-S03-16 ~ ST-S03-21（6 个，编排 delta 同名 flow 的执行实现）
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from test_s05_scenarios import BASE, T0, FakeLLM

VALID_DRAFT = {
    "timing_type": "after_months",
    "timing_value": "1",
    "reason": "你说下个月节奏会松一些",
    "confidence": 82,
}


class ProposalLLM(FakeLLM):
    """在 FakeLLM 之上加 propose_timing / summarize_preferences，模式可配。"""

    def __init__(self) -> None:
        self.mode = "ok"  # ok | unavailable
        self.propose_calls = 0
        self.draft: dict | None = dict(VALID_DRAFT)
        self.digest: str | None = "他更想和朋友一起做这些事，节奏上想慢一点。"

    async def propose_timing(self, *, wish_text: str, context: str):  # noqa: ANN201
        self.propose_calls += 1
        if self.mode == "unavailable" or self.draft is None:
            return None
        from app.agent import TimingProposalDraft

        return TimingProposalDraft(**self.draft)

    async def summarize_preferences(self, *, entries: list[str]):  # noqa: ANN201
        if self.mode == "unavailable" or self.digest is None:
            return None
        from app.agent import PreferenceDigest

        return PreferenceDigest(summary=self.digest)


@pytest.fixture
async def env(app_env: None, tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, ProposalLLM]]:
    os.environ["APP_BASE_URL"] = "http://t"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "objects")

    from app.agent import set_llm_provider
    from app.clock import clock
    from app.config import get_settings
    from app.db import dispose_engines
    from app.main import create_app
    from app.notify import InMemoryEmailSender, set_senders
    from app.storage import set_storage

    llm = ProposalLLM()
    get_settings.cache_clear()
    set_storage(None)
    set_llm_provider(llm)
    from app.notify import DisabledPushSender

    set_senders(DisabledPushSender(), InMemoryEmailSender())
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post("/api/test/clock", json={"now": T0.isoformat()})
        yield client, llm
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


def _fresh(uid: str) -> dict:
    """时钟被推远之后重签 access token（与 test_s03_scenarios 同一做法）。"""
    import uuid as _uuid

    from app.security import issue_access_token

    return {"Authorization": f"Bearer {issue_access_token(_uuid.UUID(uid))}"}


async def _subscribe(client: AsyncClient, uid: str) -> None:
    assert (await client.post("/api/test/push-subscription", json={"user_id": uid})).status_code == 204


async def _seeded(client: AsyncClient, h: dict, text: str = "想在冬天学会滑雪") -> str:
    r = await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": text})
    assert r.status_code == 201, r.text
    return r.json()["wish"]["id"]


# ---------------------------------------------------------------- UT（pydantic / DB）

from uuid import uuid4  # noqa: E402


def test_UT_S03_29_draft_timing_type_limited_to_four_time_kinds() -> None:
    """草稿只允许 4 种时间类：signal 与 none 不是「可执行的时间」（架构 5.4）。"""
    from app.agent import TimingProposalDraft

    for bad in ("when_tired", "none"):
        with pytest.raises(ValidationError):
            TimingProposalDraft(timing_type=bad, timing_value=None, reason=None, confidence=50)


def _seed_wish_owner(raw_db) -> tuple[str, str]:
    uid, wid = str(uuid4()), str(uuid4())
    raw_db.execute("INSERT INTO users (id, is_anonymous) VALUES (?, 1)", (uid,))
    raw_db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, source) VALUES (?, ?, x'00', 'text')",
        (wid, uid),
    )
    return uid, wid


def test_UT_S03_30_confidence_bounds(raw_db) -> None:
    """confidence CHECK 0–100（UT-S03-30）。"""
    uid, wid = _seed_wish_owner(raw_db)
    ok = dict(
        owner_id=uid, wish_id=wid, status="confirmed", timing_type="season", confidence=80,
        validation_result='{"valid": true}', expires_at="2026-09-10T00:00:00.000Z",
        decided_at="2026-09-03T00:00:00.000Z",
    )
    raw_db.execute(
        "INSERT INTO timing_proposals (id, owner_id, wish_id, status, timing_type,"
        " confidence, validation_result, expires_at, decided_at)"
        " VALUES (:id, :owner_id, :wish_id, :status, :timing_type, :confidence,"
        " :validation_result, :expires_at, :decided_at)",
        {"id": str(uuid4()), **ok},
    )
    with pytest.raises(Exception, match="confidence BETWEEN 0 AND 100"):
        raw_db.execute(
            "INSERT INTO timing_proposals (id, owner_id, wish_id, status, timing_type,"
            " confidence, validation_result, expires_at, decided_at)"
            " VALUES (:id, :owner_id, :wish_id, :status, :timing_type, :confidence,"
            " :validation_result, :expires_at, :decided_at)",
            {"id": str(uuid4()), **ok, "confidence": 101},
        )
    raw_db.rollback()


def test_UT_S03_31_status_enum(raw_db) -> None:
    """status 只允许 4 个枚举值（UT-S03-31）。"""
    uid, wid = _seed_wish_owner(raw_db)
    base = (
        "INSERT INTO timing_proposals (id, owner_id, wish_id, status, timing_type,"
        " confidence, validation_result, expires_at)"
        " VALUES (:id, :owner_id, :wish_id, :status, 'season', 80,"
        " '{\"valid\": true}', '2026-09-10T00:00:00.000Z')"
    )
    args = {"id": str(uuid4()), "owner_id": uid, "wish_id": wid, "status": "pending"}
    raw_db.execute(base, args)
    raw_db.commit()
    with pytest.raises(Exception, match="CHECK constraint failed"):
        raw_db.execute(base, {**args, "id": str(uuid4()), "status": "sent"})
    raw_db.rollback()


def test_UT_S03_32_decided_at_state_pairing(raw_db) -> None:
    """confirmed 必须有 decided_at；pending 必须没有（UT-S03-32）。"""
    uid, wid = _seed_wish_owner(raw_db)
    base = (
        "INSERT INTO timing_proposals (id, owner_id, wish_id, status, timing_type,"
        " confidence, validation_result, expires_at, decided_at)"
        " VALUES (:id, :owner_id, :wish_id, :status, 'season', 80,"
        " '{\"valid\": true}', '2026-09-10T00:00:00.000Z', :decided_at)"
    )
    raw_db.execute(
        base,
        {"id": str(uuid4()), "owner_id": uid, "wish_id": wid, "status": "confirmed",
         "decided_at": "2026-09-03T00:00:00.000Z"},
    )
    with pytest.raises(Exception, match="decided_state_pairing"):
        raw_db.execute(
            base,
            {"id": str(uuid4()), "owner_id": uid, "wish_id": wid, "status": "confirmed",
             "decided_at": None},
        )
    raw_db.rollback()


def test_UT_S03_33_single_pending_per_wish(raw_db) -> None:
    """部分唯一索引：同一愿望至多 1 条 pending（服务层先终结旧提议再插入）。"""
    uid, wid = str(uuid4()), str(uuid4())
    raw_db.execute("INSERT INTO users (id, is_anonymous) VALUES (?, 1)", (uid,))
    raw_db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, source) VALUES (?, ?, x'00', 'text')",
        (wid, uid),
    )
    base = (
        "INSERT INTO timing_proposals (id, owner_id, wish_id, status, timing_type,"
        ' confidence, validation_result, expires_at)'
        " VALUES (?, ?, ?, 'pending', 'season', 80, '{\"valid\": true}', '2026-09-10T00:00:00.000Z')"
    )
    raw_db.execute(base, (str(uuid4()), uid, wid))
    raw_db.commit()
    with pytest.raises(Exception, match="UNIQUE constraint failed"):
        raw_db.execute(base, (str(uuid4()), uid, wid))
    raw_db.rollback()


# ---------------------------------------------------------------- UT（HTTP 层）


async def test_UT_S03_34_evidence_holds_ids_only(env) -> None:
    """evidence 默认 '[]' 或只含 {kind,id} 引用，不含任何内容文本。"""
    client, llm = env
    h, _ = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["degraded"] is False
    p = body["proposal"]
    assert p["evidence"] == [] or all(set(e.keys()) == {"kind", "id"} for e in p["evidence"])
    assert "滑雪" not in str(p["evidence"]), "evidence 只存 ID 引用，不复制内容"


async def test_UT_S03_35_confirm_body_forbidden(env) -> None:
    """confirm 请求体必须为空——不接受客户端传入任何时间字段（EX-P.4）。"""
    client, llm = env
    h, _ = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    pid = r.json()["proposal"]["id"]
    r = await client.post(
        f"{BASE}/wishes/{wid}/timing-proposals/{pid}/confirm",
        headers=h,
        json={"next_trigger_at": "2027-01-01T00:00:00+08:00"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "PROPOSAL_CONFIRM_BODY_FORBIDDEN"


async def test_UT_S03_36_confirm_rejects_expired(env) -> None:
    """新提议替代旧 pending（P7）后，confirm 旧提议 → 409 PROPOSAL_EXPIRED。"""
    client, llm = env
    h, _ = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    old_id = r.json()["proposal"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert r.json()["proposal"]["id"] != old_id
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals/{old_id}/confirm", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PROPOSAL_EXPIRED"


async def test_UT_S03_37_invalid_draft_stored_as_expired_with_audit(env) -> None:
    """规则校验不通过（2027-02-30 不存在）：照常入库但立即 expired + reason_code 审计。"""
    client, llm = env
    llm.draft = {**VALID_DRAFT, "timing_type": "month_day", "timing_value": "2027-02-30"}
    h, _ = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert p["status"] == "expired"
    assert p["validation"]["valid"] is False
    assert p["validation"]["reason_code"] == "TIMING_INVALID"
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals/{p['id']}/confirm", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PROPOSAL_EXPIRED"
    from app.proposals import _validate_draft_payload

    assert _validate_draft_payload(
        {"type": "month_day", "month_day": "2027-02-30"}, False, "Asia/Shanghai"
    ) == {"valid": False, "reason_code": "TIMING_INVALID"}


async def test_UT_S03_38_free_weekend_requires_availability(env) -> None:
    """free_weekend 建议要求用户至少有一条可用时段（EX-P.2）。"""
    client, llm = env
    llm.draft = {
        "timing_type": "free_weekend",
        "timing_value": None,
        "reason": "找一个空闲的周末",
        "confidence": 70,
    }
    h, _ = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    p = r.json()["proposal"]
    assert p["status"] == "expired"
    assert p["validation"]["reason_code"] == "PROPOSAL_NO_AVAILABILITY"
    r = await client.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 540, "end_minute": 720},
    )
    assert r.status_code == 201
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    p = r.json()["proposal"]
    assert p["status"] == "pending" and p["validation"]["valid"] is True


async def test_UT_S03_39_expiry_scan_after_ttl(env) -> None:
    """expires_at 默认 7 天；超时提议由调度轮置 expired（第 3 层过期路径）。"""
    client, llm = env
    h, uid = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    pid = r.json()["proposal"]["id"]
    from datetime import datetime

    expires_at = datetime.fromisoformat(r.json()["proposal"]["expires_at"])
    assert expires_at - T0 <= timedelta(days=7, minutes=1)
    await client.post("/api/test/clock", json={"now": (T0 + timedelta(days=8)).isoformat()})
    r = await client.post("/api/test/scheduler/tick")
    assert r.status_code == 200
    assert r.json()["expired_proposals"] == 1
    r = await client.post(
        f"{BASE}/wishes/{wid}/timing-proposals/{pid}/confirm", headers=_fresh(uid)
    )
    assert r.status_code == 409 and r.json()["code"] == "PROPOSAL_EXPIRED"


async def test_UT_S03_40_server_computes_trigger_time(env) -> None:
    """确认后 next_trigger_at 由服务端计算；proposed_trigger_at 永不写入 wishes。"""
    client, llm = env
    h, _ = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    pid = r.json()["proposal"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals/{pid}/confirm", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wish"]["state"] == "brewing"
    assert body["wish"]["timing"]["next_trigger_at"] is not None
    from app.timing import plan_timing

    expected = plan_timing(timing_type="after_months", timezone="Asia/Shanghai", after_months=1)
    got = body["wish"]["timing"]["next_trigger_at"]
    assert str(expected.next_trigger_at)[:10] in got


# ---------------------------------------------------------------- ST


async def test_ST_S03_16_generate_confirm_then_existing_reminder_chain(env) -> None:
    """生成→展示→确认→衔接既有提醒链路：确认后的提醒行为与手动约定完全一致。"""
    client, llm = env
    h, uid = await _signup(client)
    await _subscribe(client, uid)
    wid = await _seeded(client, h)
    r = await client.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 540, "end_minute": 720},
    )
    assert r.status_code == 201
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert p["status"] == "pending" and p["validation"]["valid"] is True
    assert 0 <= p["confidence"] <= 100
    # 建议在确认前不产生任何提醒（S08 AC-03 前半句）
    r = await client.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert r.status_code == 200 and r.json()["items"] == []
    # 确认（空 body）→ brewing，proposal confirmed
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals/{p['id']}/confirm", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["wish"]["state"] == "brewing"
    assert r.json()["proposal"]["status"] == "confirmed"
    assert r.json()["proposal"]["decided_at"] is not None
    # 时钟推进 1 个月 → 调度 → outbox 恰好 1 条 delivered
    await client.post("/api/test/clock", json={"now": (T0 + timedelta(days=40)).isoformat()})
    r = await client.post("/api/test/scheduler/tick")
    assert r.json()["delivered"] >= 1
    r = await client.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["status"] == "delivered"
    assert "滑雪" in items[0]["body"], "文案仍为模板拼接、逐字引用原话摘要"
    r = await client.get(f"{BASE}/wishes/{wid}", headers=_fresh(uid))
    assert r.json()["timing_proposal"] is None


async def test_ST_S03_17_reject_writes_nothing(env) -> None:
    """拒绝建议不产生任何副作用（EX-P.3）。"""
    client, llm = env
    h, uid = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    pid = r.json()["proposal"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals/{pid}/reject", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["proposal"]["status"] == "rejected"
    assert r.json()["proposal"]["decided_at"] is not None
    r = await client.get(f"{BASE}/wishes/{wid}", headers=h)
    assert r.json()["state"] == "seeded"
    assert r.json()["timing"]["next_trigger_at"] is None
    assert r.json()["timing_proposal"] is None
    r = await client.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert r.json()["items"] == []


async def test_ST_S03_18_delete_availability_expires_pending_proposal(env) -> None:
    """依据被删除 → 建议立即失效，确认被拒（EX-P.5，编排同名 flow）。"""
    client, llm = env
    h, uid = await _signup(client)
    wid = await _seeded(client, h, "想去看海")
    llm.draft = {
        "timing_type": "free_weekend",
        "timing_value": None,
        "reason": "你说过周五上午通常有空",
        "confidence": 85,
    }
    r = await client.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 540, "end_minute": 720},
    )
    assert r.status_code == 201
    window_id = r.json()["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert r.status_code == 200, r.text
    proposal_id = r.json()["proposal"]["id"]
    # 删除依据时段（S08 Step 18）
    r = await client.delete(f"{BASE}/me/availability/{window_id}", headers=h)
    assert r.status_code == 204
    # EX-P.5：确认被拒
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals/{proposal_id}/confirm", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PROPOSAL_EXPIRED"
    # 提议状态已过期
    r = await client.get(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert next(i for i in r.json()["items"] if i["id"] == proposal_id)["status"] == "expired"


async def test_ST_S03_19_llm_degraded_no_side_effect(env) -> None:
    """LLM 降级：无落库、无错误码、零变化（EX-P.1）。"""
    client, llm = env
    llm.mode = "unavailable"
    h, _ = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"proposal": None, "degraded": True}
    r = await client.get(f"{BASE}/wishes/{wid}", headers=h)
    assert r.json()["state"] == "seeded"
    assert r.json()["timing_proposal"] is None


async def test_ST_S03_20_new_proposal_supersedes_old_pending(env) -> None:
    """再次生成：旧 pending 自动 expired，新提议 pending，任意时刻 pending ≤ 1。"""
    client, llm = env
    h, _ = await _signup(client)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    first = r.json()["proposal"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    second = r.json()["proposal"]["id"]
    assert second != first
    r = await client.get(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    items = r.json()["items"]
    assert len(items) == 2
    assert sum(1 for i in items if i["status"] == "pending") == 1
    assert next(i for i in items if i["id"] == first)["status"] == "expired"


async def test_ST_S03_21_reminder_chain_calls_no_llm_chat(env) -> None:
    """确认与调度全链路不再调用 LLM（文案为模板拼接，S03 Step 15 说明）。"""
    client, llm = env
    h, uid = await _signup(client)
    await _subscribe(client, uid)
    wid = await _seeded(client, h)
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    pid = r.json()["proposal"]["id"]
    assert llm.propose_calls == 1
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals/{pid}/confirm", headers=h)
    assert r.status_code == 200
    await client.post("/api/test/clock", json={"now": (T0 + timedelta(days=40)).isoformat()})
    r = await client.post("/api/test/scheduler/tick")
    assert r.json()["delivered"] >= 1
    assert llm.propose_calls == 1, "确认与调度阶段不再调用 propose_timing"
