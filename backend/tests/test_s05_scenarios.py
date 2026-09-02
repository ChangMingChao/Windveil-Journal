"""S05 场景测试（端到端 HTTP）。

覆盖 UT-S05-03/07/08/09/10（HTTP 层字段与状态断言）与 ST-S05-01、ST-S05-03~14。

ST-S05-02 与 UT-S05-19/20 是纯前端行为（河流视图重排、切换视图不发新请求），
由 Batch 7 的 `frontend/tests/garden.test.tsx` 与 `frontend/tests/river.test.ts` 覆盖。
ST-S05-15/16 为 [manual]（375/768/1024/1440px 目视、键盘焦点顺序），按规范不写 JSONL。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

BASE = "/api/v1"
# 固定时钟起点。每张卡种下前把时钟推后一分钟，好让 seeded_at 倒序可断言
T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone(timedelta(hours=8)))


class FakeLLM:
    """S05 不测理解质量，固定返回一份可用的理解结果即可。

    conditions.title 取自原话，这样 12 张卡的标题互不相同，断言排序时更容易读。
    """

    async def understand_wish(self, text: str):  # noqa: ANN201
        from app.agent import UnderstandResult

        return UnderstandResult.model_validate(
            {
                "understanding": {
                    "kind": "future_wish",
                    "feeling": "放松",
                    "conditions": {"title": text[:40] or "一件还没发生的事"},
                    "smallest_step": "先只是想一想",
                },
                "question": "更像一次独处吗？",
            }
        )

    async def next_step(self, *, original_text, feeling, rejected):  # noqa: ANN001, ANN201, ARG002
        from app.agent import StepSuggestion

        return StepSuggestion(
            text="只是想一想那件事", est_minutes=2, involves_cost=False, involves_others=False
        )

    async def classify_message(self, *, text, original_text):  # noqa: ANN001, ANN201, ARG002
        from app.agent import MessageReply

        return MessageReply(intent="chat", reply="嗯，我记着")


class FlakyStorage:
    """指定若干 key 永远删不掉的对象存储，用于注入 EX-28.1 的存储故障。

    其余方法一律透传给真实的 LocalObjectStorage —— 只有删除这一条路径是坏的，
    别的行为必须保持真实，否则测出来的 204 说明不了任何事。
    """

    def __init__(self, real, failing: set[str]) -> None:  # noqa: ANN001
        self._real = real
        self.failing = failing

    def presign_put(self, key, content_type, size_bytes):  # noqa: ANN001, ANN201
        return self._real.presign_put(key, content_type, size_bytes)

    def head(self, key):  # noqa: ANN001, ANN201
        return self._real.head(key)

    def delete_many(self, keys):  # noqa: ANN001, ANN201
        # 不在 failing 里的 key 交给真实存储删掉——只有这一条路径是坏的
        ok = [k for k in keys if k not in self.failing]
        failed = list(self._real.delete_many(ok)) if ok else []
        return failed + [k for k in keys if k in self.failing]


@pytest.fixture
async def env(app_env: None, tmp_path) -> AsyncIterator[AsyncClient]:  # noqa: ANN001
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
    set_storage(None)  # 让 storage 按新配置重建
    set_llm_provider(FakeLLM())
    set_senders(None, InMemoryEmailSender())
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post("/api/test/clock", json={"now": T0.isoformat()})
        yield client
    clock.set_fixed(None)
    set_llm_provider(None)
    set_senders(None, None)
    set_storage(None)
    await dispose_engines()


# ---------------------------------------------------------------- HTTP 助手


async def _at(client: AsyncClient, seconds: int) -> None:
    """把固定时钟推到 T0 + seconds。

    刻意用秒而不是分钟：access token 只有 15 分钟有效期，而 ST-S05-03 要连种 30 张卡，
    按分钟推进会在第 15 张时把自己的令牌推过期。
    """
    await client.post(
        "/api/test/clock", json={"now": (T0 + timedelta(seconds=seconds)).isoformat()}
    )


async def _signup(client: AsyncClient) -> tuple[dict, str]:
    r = await client.post(f"{BASE}/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


async def _seed(
    client: AsyncClient, h: dict, text: str, photos: list[str] | None = None
) -> str:
    payload: dict = {"source": "text", "text": text}
    if photos:
        payload["photo_media_ids"] = photos
    r = await client.post(f"{BASE}/wishes", headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()["wish"]["id"]


async def _brewing(client: AsyncClient, h: dict, text: str) -> str:
    wid = await _seed(client, h, text)
    r = await client.put(f"{BASE}/wishes/{wid}/timing", headers=h, json={"type": "free_weekend"})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "brewing"
    return wid


async def _wind(client: AsyncClient, h: dict, text: str) -> tuple[str, int]:
    wid = await _brewing(client, h, text)
    r = await client.post(f"{BASE}/wishes/{wid}/ready", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "wind"
    return wid, r.json()["version"]


async def _complete_step(client: AsyncClient, h: dict, wid: str) -> None:
    """取一个下一步并标记完成。version 每次 done 都会 +1，因此每轮重新读一次。"""
    detail = (await client.get(f"{BASE}/wishes/{wid}", headers=h)).json()
    step = (await client.post(f"{BASE}/wishes/{wid}/steps/next", headers=h)).json()["step"]
    r = await client.post(
        f"{BASE}/wishes/{wid}/steps/{step['id']}/done",
        headers={**h, "If-Match": str(detail["version"])},
    )
    assert r.status_code == 200, r.text


async def _going(client: AsyncClient, h: dict, text: str) -> str:
    wid, _ = await _wind(client, h, text)
    await _complete_step(client, h, wid)
    return wid


async def _upload_photo(client: AsyncClient, h: dict) -> str:
    r = await client.post(
        f"{BASE}/media/upload-url",
        headers=h,
        json={"kind": "image", "content_type": "image/jpeg", "size_bytes": 2048},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    put = await client.put(data["upload_url"], content=b"\xff\xd8\xff" + b"x" * 2045)
    assert put.status_code == 200, put.text
    done = await client.post(f"{BASE}/media/{data['media_id']}/complete", headers=h)
    assert done.status_code == 204, done.text
    return data["media_id"]


# ------------------------------------------------------- 前置条件与断言（直连库）
# 这些只用来造前置状态或读取断言对象，被测行为一律走 HTTP。


async def _add_pending_reminders(owner_id: str, wish_id: str, count: int) -> None:
    """造出「有待投递提醒」这个前置状态。投递本身是 S03 的被测行为，不在这里绕。"""
    from app.db import session_scope
    from app.models import ReminderOutbox

    owner = uuid.UUID(owner_id)
    async with session_scope(owner) as s:
        for n in range(count):
            s.add(
                ReminderOutbox(
                    id=uuid.uuid4(),
                    owner_id=owner,
                    wish_id=uuid.UUID(wish_id),
                    kind="timing",
                    timing_occurrence=f"pending-{n}",
                    body_enc="到了那个时候",
                    status="pending",
                )
            )


async def _pending_reminders(owner_id: str, wish_id: str) -> int:
    from sqlalchemy import func, select

    from app.db import session_scope
    from app.models import ReminderOutbox

    owner = uuid.UUID(owner_id)
    async with session_scope(owner) as s:
        return await s.scalar(
            select(func.count())
            .select_from(ReminderOutbox)
            .where(
                ReminderOutbox.owner_id == owner,
                ReminderOutbox.wish_id == uuid.UUID(wish_id),
                ReminderOutbox.status == "pending",
            )
        )


async def _count_amendments(owner_id: str, wish_id: str) -> int:
    from sqlalchemy import func, select

    from app.db import session_scope
    from app.models import WishAmendment

    owner = uuid.UUID(owner_id)
    async with session_scope(owner) as s:
        return await s.scalar(
            select(func.count())
            .select_from(WishAmendment)
            .where(WishAmendment.owner_id == owner, WishAmendment.wish_id == uuid.UUID(wish_id))
        )


CHILD_TABLES = ("wish_photos", "wish_steps", "wish_messages", "wish_amendments", "reminder_outbox")


async def _child_row_counts(owner_id: str, wish_id: str) -> dict[str, int]:
    """5 张子表里与该愿望相关的行数——彻底删除的级联断言对象（UT-S05-15 / ST-S05-06）。"""
    from sqlalchemy import text as sql_text

    from app.db import session_scope

    out: dict[str, int] = {}
    async with session_scope(uuid.UUID(owner_id)) as s:
        # wish_photos 是关联表，不冗余 owner_id，按父表主键限定即通过 owner_guard
        out["wish_photos"] = (
            await s.execute(
                sql_text("SELECT count(*) FROM wish_photos WHERE wish_id = :w"), {"w": wish_id}
            )
        ).scalar_one()
        # 表名来自本模块内的字面量元组 CHILD_TABLES，不来自入参
        for table in CHILD_TABLES[1:]:
            out[table] = (
                await s.execute(
                    sql_text(
                        f"SELECT count(*) FROM {table} WHERE wish_id = :w AND owner_id = :o"  # noqa: S608
                    ),
                    {"w": wish_id, "o": owner_id},
                )
            ).scalar_one()
    return out


async def _object_keys(owner_id: str, media_ids: list[str]) -> list[str]:
    from app.db import session_scope
    from app.models import Media

    async with session_scope(uuid.UUID(owner_id)) as s:
        keys = []
        for mid in media_ids:
            media = await s.get(Media, uuid.UUID(mid))
            assert media is not None
            keys.append(media.object_key)
        return keys


async def _orphan_keys() -> list[str]:
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import OrphanObject

    async with session_scope() as s:
        return [o.object_key for o in (await s.scalars(select(OrphanObject))).all()]


async def _force_state(owner_id: str, wish_id: str, state: str) -> None:
    """直接置状态。happened 由 S06 的记忆页发布产生（Batch 6 尚未交付），这里只造前置。"""
    from app.db import session_scope
    from app.models import Wish

    async with session_scope(uuid.UUID(owner_id)) as s:
        wish = await s.get(Wish, uuid.UUID(wish_id))
        assert wish is not None
        wish.state = state


# ---------------------------------------------------------------- UT（HTTP 层）


async def test_UT_S05_03_limit_boundaries(env: AsyncClient) -> None:
    """limit 边界：1 与 50 通过，0 与 51 被拒（listWishes → limit.minimum/maximum）。"""
    h, _ = await _signup(env)
    await _seed(env, h, "想去看一次海")
    for limit, expected in ((1, 200), (50, 200), (0, 422), (51, 422)):
        r = await env.get(f"{BASE}/wishes", headers=h, params={"limit": limit})
        assert r.status_code == expected, f"limit={limit}"
        if expected == 422:
            assert r.json()["code"] == "VALIDATION_FAILED"


async def test_UT_S05_07_amend_requires_at_least_one_field(env: AsyncClient) -> None:
    """amendWish 的 minProperties: 1 —— 空对象没有任何要改的东西。"""
    h, _ = await _signup(env)
    wid = await _seed(env, h, "想学会滑雪")
    r = await env.patch(f"{BASE}/wishes/{wid}", headers=h, json={})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_FAILED"


async def test_UT_S05_08_title_length_boundary(env: AsyncClient) -> None:
    """title.maxLength: 60 —— 60 字通过，61 字拒绝。"""
    h, _ = await _signup(env)
    wid = await _seed(env, h, "想学会滑雪")
    ok = await env.patch(f"{BASE}/wishes/{wid}", headers=h, json={"title": "滑" * 60})
    assert ok.status_code == 200, ok.text
    assert ok.json()["title"] == "滑" * 60
    too_long = await env.patch(f"{BASE}/wishes/{wid}", headers=h, json={"title": "滑" * 61})
    assert too_long.status_code == 422
    assert too_long.json()["code"] == "VALIDATION_FAILED"


async def test_UT_S05_09_delete_without_confirm_is_rejected(env: AsyncClient) -> None:
    """confirm 是服务端强制的必填参数，缺失时不删除任何数据（EX-25.1）。"""
    h, _ = await _signup(env)
    wid = await _seed(env, h, "想去看一次海")
    r = await env.delete(f"{BASE}/wishes/{wid}", headers=h)
    assert r.status_code == 400
    assert r.json()["code"] == "CONFIRMATION_REQUIRED"
    assert (await env.get(f"{BASE}/wishes/{wid}", headers=h)).status_code == 200


async def test_UT_S05_10_delete_with_confirm_false_is_rejected(env: AsyncClient) -> None:
    """confirm.const: true —— 显式传 false 与不传一样被拒。"""
    h, _ = await _signup(env)
    wid = await _seed(env, h, "想去看一次海")
    r = await env.delete(f"{BASE}/wishes/{wid}", headers=h, params={"confirm": "false"})
    assert r.status_code == 400
    assert r.json()["code"] == "CONFIRMATION_REQUIRED"
    assert (await env.get(f"{BASE}/wishes/{wid}", headers=h)).status_code == 200


# ---------------------------------------------------------------- ST：S05.1 浏览

FORBIDDEN_COUNTERS = ("total", "completed_count", "overdue_count", "overdue", "progress", "count")


async def test_ST_S05_01_browse_by_state_and_deep_link(env: AsyncClient) -> None:
    """Step 1→12：12 张卡分布在 4 种状态，先看全部再按状态筛选。"""
    h, _ = await _signup(env)
    order: list[str] = []
    brewing: list[str] = []
    tick = 0
    for i in range(3):
        await _at(env, tick)
        order.append(await _seed(env, h, f"只是种下 {i}"))
        await _at(env, tick + 1)
        wid = await _brewing(env, h, f"正在酝酿 {i}")
        order.append(wid)
        brewing.append(wid)
        await _at(env, tick + 2)
        wid, _ = await _wind(env, h, f"风来了 {i}")
        order.append(wid)
        await _at(env, tick + 3)
        order.append(await _going(env, h, f"正在进行 {i}"))
        tick += 4

    r = await env.get(f"{BASE}/wishes", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "next_cursor"}
    for forbidden in FORBIDDEN_COUNTERS:
        assert forbidden not in body
    assert len(body["items"]) == 12
    assert [i["id"] for i in body["items"]] == list(reversed(order))  # seeded_at 倒序
    assert {i["state"] for i in body["items"]} == {"seeded", "brewing", "wind", "going"}
    for item in body["items"]:
        assert item["timing"]["label"]  # 每条都带时机文案
        assert item["state"]

    filtered = await env.get(f"{BASE}/wishes", headers=h, params={"state": "brewing"})
    assert filtered.status_code == 200
    items = filtered.json()["items"]
    assert sorted(i["id"] for i in items) == sorted(brewing)
    assert {i["state"] for i in items} == {"brewing"}


@pytest.mark.skip(
    reason="Step 13→14 是纯前端重排，已由 frontend/tests/garden.test.tsx 覆盖（Batch 7）"
)
async def test_placeholder_view_switch_lives_in_frontend() -> None:
    """河流视图重排发生在浏览器内存里：同一批数据换个排序键，不打接口。

    「不发新请求」这条断言只能在前端侧成立——服务端观察不到一次没有发生的请求。
    Batch 7 已在 `frontend/tests/garden.test.tsx` 用 Testing Library + 计数过的
    fetch 替身实现了 ST-S05-02（与 UT-S05-19/20），因此本函数刻意**不带用例 ID**：
    带 ID 会让同一个 ST-S05-02 在 JSONL 里出现两条记录（一条 skip 一条 pass）。
    """


async def test_ST_S05_03_cursor_pagination(env: AsyncClient) -> None:
    """Step 2→5：30 张卡分两页取完，无重叠无遗漏，第二页 next_cursor 为 null。"""
    h, _ = await _signup(env)
    created: list[str] = []
    for i in range(30):
        await _at(env, i)
        created.append(await _seed(env, h, f"第 {i} 件还没发生的事"))

    first = await env.get(f"{BASE}/wishes", headers=h)
    assert first.status_code == 200
    p1 = first.json()
    assert len(p1["items"]) == 20  # limit 缺省为 20
    assert p1["next_cursor"]

    second = await env.get(f"{BASE}/wishes", headers=h, params={"cursor": p1["next_cursor"]})
    assert second.status_code == 200
    p2 = second.json()
    assert len(p2["items"]) == 10
    assert p2["next_cursor"] is None

    ids1 = [i["id"] for i in p1["items"]]
    ids2 = [i["id"] for i in p2["items"]]
    assert not set(ids1) & set(ids2)
    assert sorted(ids1 + ids2) == sorted(created)
    assert ids1 + ids2 == list(reversed(created))


# ---------------------------------------------------------------- ST：S05.2 整理

BANNED_WORDS = ("失败", "放弃", "未完成")


async def test_ST_S05_04_let_go_quietly(env: AsyncClient) -> None:
    """Step 15→22：安静放下——掐断提醒，但标题、原话、种下时间一个都不动。"""
    h, uid = await _signup(env)
    wid = await _brewing(env, h, "想一个人去海边待两天")
    before = (await env.get(f"{BASE}/wishes/{wid}", headers=h)).json()
    await _add_pending_reminders(uid, wid, 2)
    assert await _pending_reminders(uid, wid) == 2

    r = await env.post(f"{BASE}/wishes/{wid}/let-go", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "let_go"
    assert body["timing"]["next_trigger_at"] is None
    assert body["title"] == before["title"]
    assert body["original_text"] == before["original_text"]
    assert body["seeded_at"] == before["seeded_at"]
    # 放下必须同时掐断提醒队列：这是这个产品最不能出的错
    assert await _pending_reminders(uid, wid) == 0
    for banned in BANNED_WORDS:
        assert banned not in r.text

    listed = await env.get(f"{BASE}/wishes", headers=h, params={"state": "let_go"})
    assert [i["id"] for i in listed.json()["items"]] == [wid]


async def test_ST_S05_05_amend_a_wish(env: AsyncClient) -> None:
    """Step 15「改一改它」：标题更新，原话与种下时间保留，修订留一份快照。"""
    h, uid = await _signup(env)
    wid = await _seed(env, h, "学会滑雪")
    before = (await env.get(f"{BASE}/wishes/{wid}", headers=h)).json()

    r = await env.patch(f"{BASE}/wishes/{wid}", headers=h, json={"title": "和朋友学会滑雪"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "和朋友学会滑雪"
    assert body["original_text"] == before["original_text"] == "学会滑雪"
    assert body["seeded_at"] == before["seeded_at"]
    assert await _count_amendments(uid, wid) == 1
    # 响应里没有任何「改过几次」的计数——修改不该被记成账
    for forbidden in ("amend_count", "revision_count", "edit_count"):
        assert forbidden not in body


async def test_ST_S05_06_permanent_delete_full_chain(env: AsyncClient) -> None:
    """Step 23→32：2 媒体 + 3 步骤 + 2 对话 + 1 修订 + 1 提醒，一并清空。"""
    h, uid = await _signup(env)
    photo_ids = [await _upload_photo(env, h), await _upload_photo(env, h)]
    wid = await _seed(env, h, "一件要被彻底删除的事", photos=photo_ids)
    keys = await _object_keys(uid, photo_ids)

    assert (
        await env.put(f"{BASE}/wishes/{wid}/timing", headers=h, json={"type": "free_weekend"})
    ).status_code == 200
    assert (await env.post(f"{BASE}/wishes/{wid}/ready", headers=h)).status_code == 200
    for _ in range(3):
        await _complete_step(env, h, wid)
    for text in ("今天先不动它", "还是想去"):
        assert (
            await env.post(f"{BASE}/wishes/{wid}/messages", headers=h, json={"text": text})
        ).status_code == 200
    assert (
        await env.patch(f"{BASE}/wishes/{wid}", headers=h, json={"title": "改过一次的标题"})
    ).status_code == 200
    await _add_pending_reminders(uid, wid, 1)

    # 2 次对话各留下「用户一句 + Agent 一句」，因此 wish_messages 是 4 行
    assert await _child_row_counts(uid, wid) == {
        "wish_photos": 2,
        "wish_steps": 3,
        "wish_messages": 4,
        "wish_amendments": 1,
        "reminder_outbox": 1,
    }
    from app.storage import get_storage

    assert all(get_storage().head(k) is not None for k in keys)

    d = await env.delete(f"{BASE}/wishes/{wid}", headers=h, params={"confirm": "true"})
    assert d.status_code == 204, d.text
    assert all(get_storage().head(k) is None for k in keys)
    assert await _child_row_counts(uid, wid) == dict.fromkeys(CHILD_TABLES, 0)
    assert (await env.get(f"{BASE}/wishes/{wid}", headers=h)).status_code == 404


# ---------------------------------------------------------------- ST：异常路径


async def test_ST_S05_07_stale_cursor_is_rejected(env: AsyncClient) -> None:
    """EX-2.1：游标锚点被彻底删除后，翻页返回 400，客户端丢弃游标重取第一页。"""
    h, _ = await _signup(env)
    ids: list[str] = []
    for i in range(3):
        await _at(env, i)
        ids.append(await _seed(env, h, f"第 {i} 件事"))

    page = await env.get(f"{BASE}/wishes", headers=h, params={"limit": 1})
    cursor = page.json()["next_cursor"]
    assert cursor
    assert (
        await env.delete(f"{BASE}/wishes/{ids[-1]}", headers=h, params={"confirm": "true"})
    ).status_code == 204

    stale = await env.get(f"{BASE}/wishes", headers=h, params={"cursor": cursor})
    assert stale.status_code == 400
    assert stale.json()["code"] == "CURSOR_INVALID"

    retry = await env.get(f"{BASE}/wishes", headers=h)  # 用户只感知为一次刷新
    assert retry.status_code == 200
    assert [i["id"] for i in retry.json()["items"]] == list(reversed(ids[:2]))


async def test_ST_S05_08_foreign_wish_returns_404_and_audits(
    env: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """EX-3.1：越权访问返回 404 而不是 403，并留一条只含标识符的审计日志。"""
    from app.audit import LOGGER_NAME

    h_b, _ = await _signup(env)
    wid_b = await _seed(env, h_b, "B 的一件很私密的事")
    h_a, uid_a = await _signup(env)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        r = await env.get(f"{BASE}/wishes/{wid_b}", headers=h_a)
    assert r.status_code == 404  # 403 会泄露「这个 ID 确实存在」
    assert r.json()["code"] == "WISH_NOT_FOUND"

    records = [rec for rec in caplog.records if rec.name == LOGGER_NAME]
    assert len(records) == 1
    message = records[0].getMessage()
    assert uid_a in message
    assert wid_b in message
    assert "私密" not in message  # 审计日志不能成为第二个泄露面


async def test_ST_S05_09_empty_garden(env: AsyncClient) -> None:
    """EX-6.1：花园为空时也不给任何数字——响应里只有 items 与 next_cursor。"""
    h, _ = await _signup(env)
    r = await env.get(f"{BASE}/wishes", headers=h)
    assert r.status_code == 200
    assert r.json() == {"items": [], "next_cursor": None}


async def test_ST_S05_10_state_with_no_cards(env: AsyncClient) -> None:
    """EX-9.1：某状态下无卡片时返回空列表，不自动回退为 all。"""
    h, _ = await _signup(env)
    await _seed(env, h, "只是种下")
    r = await env.get(f"{BASE}/wishes", headers=h, params={"state": "going"})
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert len((await env.get(f"{BASE}/wishes", headers=h)).json()["items"]) == 1


async def test_ST_S05_11_let_go_in_terminal_state(env: AsyncClient) -> None:
    """EX-17.1：已经发生的事不能被放下，且一个字段都不许改动。"""
    h, uid = await _signup(env)
    wid = await _brewing(env, h, "想去看一次雪")
    await _force_state(uid, wid, "happened")
    before = (await env.get(f"{BASE}/wishes/{wid}", headers=h)).json()

    r = await env.post(f"{BASE}/wishes/{wid}/let-go", headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
    assert (await env.get(f"{BASE}/wishes/{wid}", headers=h)).json() == before


async def test_ST_S05_12_delete_without_confirmation(env: AsyncClient) -> None:
    """EX-25.1：二次确认是服务端强制的，任何调用方都绕不过去。"""
    h, _ = await _signup(env)
    wid = await _seed(env, h, "想去看一次海")
    r = await env.delete(f"{BASE}/wishes/{wid}", headers=h)
    assert r.status_code == 400
    assert r.json()["code"] == "CONFIRMATION_REQUIRED"
    assert (await env.get(f"{BASE}/wishes/{wid}", headers=h)).status_code == 200
    assert (
        await env.delete(f"{BASE}/wishes/{wid}", headers=h, params={"confirm": "true"})
    ).status_code == 204


async def test_ST_S05_13_partial_object_failure_converges(env: AsyncClient) -> None:
    """EX-28.1：存储故障不阻塞删除意图，残留 key 由每日清理任务收敛。"""
    from app.db import session_scope
    from app.services import retry_orphan_objects
    from app.storage import get_storage, set_storage

    h, uid = await _signup(env)
    photo_ids = [await _upload_photo(env, h), await _upload_photo(env, h)]
    wid = await _seed(env, h, "带着两张照片的愿望", photos=photo_ids)
    keys = await _object_keys(uid, photo_ids)
    real = get_storage()

    set_storage(FlakyStorage(real, failing={keys[0]}))
    try:
        r = await env.delete(f"{BASE}/wishes/{wid}", headers=h, params={"confirm": "true"})
    finally:
        set_storage(real)
    assert r.status_code == 204, r.text  # 用户的删除意图立即生效
    assert (await env.get(f"{BASE}/wishes/{wid}", headers=h)).status_code == 404
    assert await _orphan_keys() == [keys[0]]
    assert real.head(keys[0]) is not None  # 残留对象确实还在存储里
    assert real.head(keys[1]) is None

    # 每日清理任务：存储恢复后重试一次，残留在后台收敛
    async with session_scope() as s:
        assert await retry_orphan_objects(s) == (1, 0)
    assert await _orphan_keys() == []
    assert real.head(keys[0]) is None


async def test_ST_S05_14_repeated_delete_is_idempotent(env: AsyncClient) -> None:
    """EX-30.1：双击或重试重复删除同一愿望，一律 204，不抛异常。"""
    h, _ = await _signup(env)
    wid = await _seed(env, h, "想去看一次海")
    for _ in range(3):
        r = await env.delete(f"{BASE}/wishes/{wid}", headers=h, params={"confirm": "true"})
        assert r.status_code == 204, r.text
