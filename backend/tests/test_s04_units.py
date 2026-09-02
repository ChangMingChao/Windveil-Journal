"""S04 单元测试：步骤合规自检与兜底库（纯函数，不依赖数据库）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent import (
    FALLBACK_DEFAULT,
    FALLBACK_STEPS,
    MessageReply,
    StepSuggestion,
    fallback_step,
)


def _suggestion(**kw: object) -> StepSuggestion:
    base = {"text": "今晚花两分钟收藏一张海的照片", "est_minutes": 2,
            "involves_cost": False, "involves_others": False}
    base.update(kw)
    return StepSuggestion(**base)  # type: ignore[arg-type]


def test_UT_S04_18_cost_flag_makes_step_non_compliant() -> None:
    """模型自报 involves_cost=true 即判定不合规，由服务端拦下并重试。"""
    assert _suggestion().compliant is True
    assert _suggestion(involves_cost=True).compliant is False
    assert _suggestion(involves_others=True).compliant is False
    assert _suggestion(est_minutes=6).compliant is False
    # 三个自检字段都是必填：模型不能靠省略字段绕过校验
    with pytest.raises(ValidationError):
        StepSuggestion(text="x", est_minutes=2, involves_cost=False)  # type: ignore[call-arg]


def test_UT_S04_19_fallback_step_is_always_compliant() -> None:
    """兜底步骤按 feeling 选取，且必然满足三项约束（EX-8.2 的最后一道防线）。"""
    for feeling in [*FALLBACK_STEPS, None, "未知感受"]:
        step = fallback_step(feeling)
        assert step.compliant is True
        assert step.est_minutes <= 5
        assert step.involves_cost is False
        assert step.involves_others is False
        # 文案不得出现产品禁用词
        for banned in ("任务", "截止", "逾期", "打卡"):
            assert banned not in step.text
    assert fallback_step("放松").text == FALLBACK_STEPS["放松"]
    assert fallback_step("没有这个感受").text == FALLBACK_DEFAULT


def test_UT_S04_15_message_intent_enum_is_closed() -> None:
    """intent 只有四个取值；模型返回别的值等同不可用。"""
    for ok in ("chat", "amend", "assist", "fatigue"):
        assert MessageReply(intent=ok, reply="好").intent == ok
    with pytest.raises(ValidationError):
        MessageReply(intent="delete", reply="好")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        MessageReply(intent="chat", reply="x" * 201)
