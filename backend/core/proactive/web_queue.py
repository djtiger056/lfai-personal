"""Web 端主动消息队列

负责管理 Web 前端轮询获取的主动消息队列。
从 ProactiveChatScheduler 中提取。
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from .models import ProactiveTargetState


def enqueue_message(
    state: ProactiveTargetState,
    payload: Union[str, Dict[str, Any]],
    now: datetime,
) -> None:
    """将主动消息加入 Web 端待取队列。

    Args:
        state: 目标状态
        payload: 文本或包含 text/image 的字典
        now: 当前时间
    """
    message_payload: Dict[str, Any] = {
        "id": f"web-{state.next_web_message_id}",
        "created_at": now.isoformat(),
        "source": "proactive",
    }
    state.next_web_message_id += 1

    if isinstance(payload, dict):
        text = str(payload.get("text") or "").strip()
        if text:
            message_payload["content"] = text
        image_bytes = payload.get("image")
        if isinstance(image_bytes, (bytes, bytearray)):
            message_payload["image_base64"] = base64.b64encode(image_bytes).decode("utf-8")
    else:
        message_payload["content"] = str(payload)

    if message_payload.get("content") or message_payload.get("image_base64"):
        state.web_pending_messages.append(message_payload)


def poll_messages(
    state: Optional[ProactiveTargetState],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """从 Web 端队列中取出消息。

    Args:
        state: 目标状态（可能为 None）
        limit: 最大取出数量

    Returns:
        消息列表
    """
    if not state or not state.web_pending_messages:
        return []
    safe_limit = max(1, min(limit, 100))
    messages = state.web_pending_messages[:safe_limit]
    state.web_pending_messages = state.web_pending_messages[safe_limit:]
    return messages
