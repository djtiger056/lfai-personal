"""主动聊天子包

将原来的 core/proactive.py 拆分为：
- models.py: 数据模型（WindowState, ProactiveTargetState）
- behavior.py: 行为规则判断（follow-up, inactivity）
- message_builder.py: 指令构建
- web_queue.py: Web 端消息队列
- scheduler.py: 调度器主体
"""

from .models import WindowState, ProactiveTargetState
from .scheduler import ProactiveChatScheduler
from .behavior import (
    should_schedule_conversation_follow_up,
    build_follow_up_instruction,
    build_inactivity_instruction,
)
from .message_builder import build_instruction
from .web_queue import enqueue_message, poll_messages

__all__ = [
    "ProactiveChatScheduler",
    "WindowState",
    "ProactiveTargetState",
    "should_schedule_conversation_follow_up",
    "build_follow_up_instruction",
    "build_inactivity_instruction",
    "build_instruction",
    "enqueue_message",
    "poll_messages",
]
