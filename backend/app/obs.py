"""日志与请求标识。

部署方案 §7-12 与 SMOKE-core-18 要求：抽查最近 100 条应用日志，**含 `request_id`
且不含愿望原话**。前半句需要每条日志都带上请求标识，后半句靠「日志里只记
标识符和类型，不记内容」的既有纪律——加密在应用层，数据库侧已无明文泄露路径，
日志就成了最后一个可能漏内容的地方。

`request_id` 走 ContextVar 而不是显式参数：它要出现在每一条日志里，
包括第三方库（SQLAlchemy、uvicorn）打的那些，而那些调用栈没法传参数进去。
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = (
    '{"level":"%(levelname)s","logger":"%(name)s",'
    '"request_id":"%(request_id)s","msg":"%(message)s"}'
)


class RequestIdFilter(logging.Filter):
    """给每条记录补上 request_id。挂在 handler 上，覆盖所有 logger。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """幂等地装配根 handler。api 与 scheduler 两个入口都调用它。"""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]
