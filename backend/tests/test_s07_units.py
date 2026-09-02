"""S07 唤回功能单元测试。"""
import inspect
from pathlib import Path

from app.models import Wish
from app.schemas import WishCard
from app.tidy import ALLOWED_STATES, list_wishes_page, recall_wish

ROOT = Path(__file__).resolve().parents[2]

def test_UT_S07_01_recall_route_contract():
    text=(ROOT/"backend/app/api.py").read_text(encoding="utf-8")
    assert '"/wishes/{wish_id}/recall"' in text and "post_recall" in text

def test_UT_S07_02_card_exposes_nullable_let_go_at():
    assert "let_go_at" in WishCard.model_fields
    assert WishCard.model_fields["let_go_at"].is_required() is False

def test_UT_S07_03_wish_model_has_nullable_column():
    assert Wish.let_go_at.property.columns[0].nullable is True

def test_UT_S07_04_state_constraint_is_declared():
    assert any(
        c.name == "wishes_let_go_timestamp_matches_state"
        for c in Wish.__table__.constraints
    )

def test_UT_S07_05_let_go_records_timestamp():
    source=inspect.getsource(__import__("app.tidy", fromlist=["let_go_wish"]).let_go_wish)
    assert "wish.let_go_at = clock.now()" in source

def test_UT_S07_06_let_go_list_orders_by_timestamp():
    source=inspect.getsource(list_wishes_page)
    assert "Wish.let_go_at.desc()" in source and 'state == "let_go"' in source

def test_UT_S07_07_legacy_null_timestamp_is_supported():
    assert "nulls_last" in inspect.getsource(list_wishes_page)

def test_UT_S07_08_recall_rejects_other_states():
    assert 'wish.state != "let_go"' in inspect.getsource(recall_wish)

def test_UT_S07_09_recall_returns_seeded():
    assert 'wish.state = "seeded"' in inspect.getsource(recall_wish)

def test_UT_S07_10_recall_clears_timing():
    source=inspect.getsource(recall_wish)
    for field in (
        "timing_type", "timing_value", "timing_set_at", "next_trigger_at", "timing_occurrence"
    ):
        assert f"wish.{field} = None" in source
    assert 'wish.trigger_kind = "none"' in source and "wish.soft_deferred = False" in source

def test_UT_S07_11_recall_does_not_overwrite_content():
    source=inspect.getsource(recall_wish)
    assert "original_text" not in source
    assert "understanding" not in source
    assert "seeded_at" not in source

def test_UT_S07_12_recall_has_no_new_reminder_insert():
    source=inspect.getsource(recall_wish)
    assert "ReminderOutbox" in source and "delete(" in source and "session.add" not in source

def test_UT_S07_13_recall_deletes_pending_reminders():
    assert 'ReminderOutbox.status == "pending"' in inspect.getsource(recall_wish)

def test_UT_S07_14_recall_does_not_call_agents():
    source=inspect.getsource(recall_wish)
    assert "get_llm_provider" not in source and "get_asr_provider" not in source

def test_UT_S07_15_detail_is_owner_scoped():
    text=(ROOT/"backend/app/api.py").read_text(encoding="utf-8")
    assert "wish.owner_id != user_id" in text and "WISH_NOT_FOUND" in text

def test_UT_S07_16_recall_conflict_is_domain_error():
    assert '"STATE_TRANSITION_NOT_ALLOWED"' in inspect.getsource(recall_wish)

def test_UT_S07_17_recall_has_no_body():
    text=(ROOT/"backend/app/api.py").read_text(encoding="utf-8")
    line=next(x for x in text.splitlines() if "async def post_recall" in x)
    assert "payload" not in line

def test_UT_S07_18_states_include_let_go():
    assert "let_go" in ALLOWED_STATES

def test_UT_S07_19_recall_is_single_write_action():
    source=inspect.getsource(recall_wish)
    assert source.count("wish.state =") == 1

def test_UT_S07_20_copy_has_no_banned_words():
    text=(ROOT/"frontend/src/pages/WishDetail.tsx").read_text(encoding="utf-8")
    for word in ("放弃", "未完成", "失败", "逾期", "完成率"):
        assert word not in text


def test_db_rejects_timestamp_on_non_let_go(raw_db):
    raw_db.execute(
        "INSERT INTO users (id, is_anonymous, timezone) VALUES (?, 1, 'Asia/Shanghai')",
        ("user-s07",),
    )
    with __import__("pytest").raises(Exception):
        raw_db.execute(
            "INSERT INTO wishes (id, owner_id, title_enc, source, state, let_go_at) "
            "VALUES (?, ?, ?, 'text', 'seeded', ?)",
            ("wish-s07", "user-s07", "标题", "2026-09-02T12:00:00Z"),
        )

