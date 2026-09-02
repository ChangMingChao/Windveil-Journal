"""S05 单元测试：列表参数、游标编解码、文案禁用词（纯函数）。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.schemas import WishListResponse
from app.services import DomainError
from app.tidy import ALLOWED_STATES, Cursor


def test_UT_S05_01_state_enum_is_closed() -> None:
    assert set(ALLOWED_STATES) == {
        "all", "seeded", "brewing", "wind", "going", "happened", "let_go"
    }
    assert "overdue" not in ALLOWED_STATES


def test_UT_S05_02_state_defaults_to_all() -> None:
    import inspect

    from app.tidy import list_wishes_page

    assert inspect.signature(list_wishes_page).parameters["state"].default == "all"


def test_UT_S05_04_limit_defaults_to_twenty() -> None:
    import inspect

    from app.tidy import list_wishes_page

    assert inspect.signature(list_wishes_page).parameters["limit"].default == 20


def test_UT_S05_05_invalid_cursor_is_rejected() -> None:
    for bad in ("!!!", "notbase64@@", Cursor.encode.__name__, "YWJj"):
        with pytest.raises(DomainError) as exc:
            Cursor.decode(bad)
        assert exc.value.code == "CURSOR_INVALID"
        assert exc.value.status == 400


def test_cursor_roundtrip_is_stable() -> None:
    """游标必须能稳定往返，否则第二页会漏数据。

    刻意不叫 UT-S05-05b：reporter 从函数名提取用例 ID，带后缀会重复写一条
    UT-S05-05 记录，让 JSONL 里同一 ID 出现两次。这是对 UT-S05-05 的补强断言，
    本身不是规格里的独立用例，因此不占 ID。
    """
    original = Cursor(datetime(2026, 9, 1, 12, 0, tzinfo=UTC), uuid.uuid4())
    decoded = Cursor.decode(original.encode())
    assert decoded.wish_id == original.wish_id
    assert decoded.seeded_at == original.seeded_at


def test_UT_S05_06_list_response_has_no_counters() -> None:
    """响应模型只有 items 与 next_cursor —— 前端在结构上拿不到可制造压迫感的数字。"""
    fields = set(WishListResponse.model_fields)
    assert fields == {"items", "next_cursor"}
    for forbidden in ("total", "completed_count", "overdue_count", "progress"):
        assert forbidden not in fields


def test_UT_S05_23_let_go_wording_has_no_failure_words() -> None:
    """放下的所有面向用户文案不得出现失败 / 放弃 / 未完成。"""
    import inspect

    from app import tidy

    src = inspect.getsource(tidy.let_go_wish)
    for banned in ("失败", "放弃", "未完成"):
        assert banned not in src


def test_UT_S05_24_delete_order_is_objects_then_records() -> None:
    """先删对象、后删记录：反过来一旦对象删除失败就再也查不到该删哪些 key。"""
    import inspect

    from app import tidy

    src = inspect.getsource(tidy.delete_wish_permanently)
    assert src.index("delete_many") < src.index("session.delete(wish)")
