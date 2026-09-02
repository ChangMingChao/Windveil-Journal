"""安全审计日志。

S05 EX-3.1：请求不属于自己的愿望必须返回 **404 而不是 403**——403 会泄露
「这个 ID 确实存在」，对一个主打私密的产品是不可接受的信息泄露。
但服务端仍然需要留痕，因此在返回 404 的同一处记一条审计日志。

日志里**只有标识符**：`user_id` 与被请求的资源 id。标题、原话、理解结果一律不写入——
审计日志本身不能成为第二个泄露面（EX-3.1 副作用逐字要求）。
"""

from __future__ import annotations

import logging
from uuid import UUID

LOGGER_NAME = "app.audit"

_log = logging.getLogger(LOGGER_NAME)


def log_denied_resource_access(
    user_id: UUID, resource: str, resource_id: UUID | str
) -> None:
    """记录一次「不存在或不属于当前用户」的资源访问尝试。

    刻意不区分「不存在」与「属于别人」：这两者在响应上必须无法区分，
    在日志上也没有区分的必要——两者都只是一次未命中的访问。
    """
    _log.warning(
        "denied_resource_access user_id=%s resource=%s resource_id=%s",
        user_id,
        resource,
        resource_id,
    )
