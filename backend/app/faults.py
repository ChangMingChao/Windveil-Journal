"""故障注入夹具。

有几条异常路径无法用「构造合适的输入」触发——数据库连不上、某张表写入失败，
这类故障只能从外部注入。测试用例里 ST-S01-03（DB 连接不可用）与 ST-S01-04
（`onboarding_answers` 写入被强制失败）就是这样的用例。

两条纪律：

  1. 只在 `APP_ENV in (local, test)` 下可武装。武装入口是 `/api/test/faults`，
     而它本身挂在 `test_router` 上——生产构建里这个路由不存在（SMOKE-core-04）。
  2. 注入点抛出的是**真实故障会抛的异常类型**（`OperationalError`），不是一个
     自定义标记异常。否则测出来的只是「代码能捕获我编的异常」，
     而不是「代码能捕获数据库真的挂了」。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("app.faults")

# 可注入的故障点。名字即注入点，写在这里是为了让「有哪些故障可注入」一目了然。
FAULT_POINTS = frozenset(
    {
        "db",  # 任何 session_scope() 打开事务时失败（ST-S01-03）
        "onboarding_answers_write",  # 初始记忆写入失败（ST-S01-04）
    }
)

_armed: frozenset[str] = frozenset()


def set_armed(names: list[str] | tuple[str, ...]) -> frozenset[str]:
    """武装一组故障点。传空列表即全部解除。返回实际生效的集合。"""
    global _armed
    unknown = set(names) - FAULT_POINTS
    if unknown:
        raise ValueError(f"unknown fault points: {sorted(unknown)}")
    _armed = frozenset(names)
    if _armed:
        logger.warning("faults_armed", extra={"points": sorted(_armed)})
    return _armed


def armed() -> frozenset[str]:
    return _armed


def check_fault(name: str) -> None:
    """在注入点调用。未武装时零开销地返回。"""
    if name not in _armed:
        return
    from sqlalchemy.exc import OperationalError

    raise OperationalError(
        "-- injected fault", None, Exception("unable to open database file")
    )
