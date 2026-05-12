"""主动聊天行为规则判断

负责 follow-up（对话追踪）和 inactivity（不活跃问候）的判断逻辑。
从 ProactiveChatScheduler 中提取。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


# 对话结束关键词
CONVERSATION_END_KEYWORDS = (
    "晚安", "拜拜", "下次聊", "先这样", "先不聊", "先忙", "回头聊", "睡了", "88", "bye", "good night"
)

# 追踪短语（助手发出的开放性话题）
FOLLOW_UP_PHRASES = (
    "然后呢", "后来呢", "你呢", "要不要", "想不想", "等你", "回我", "记得告诉我",
    "方便的话", "有空的话", "跟我说说", "展开讲讲", "我想听", "和我说"
)

# 用户开放话题关键词
OPEN_TOPIC_KEYWORDS = (
    "明天", "待会", "等会", "之后", "最近", "项目", "工作", "考试", "面试", "生病",
    "睡不着", "回家", "旅行", "聚会", "计划", "准备", "纠结", "担心", "烦", "开心"
)


def should_schedule_conversation_follow_up(
    last_user_message: str,
    assistant_message: str,
) -> Optional[str]:
    """判断是否应该安排对话追踪。

    Returns:
        追踪原因字符串，如果不需要追踪则返回 None
    """
    user_text = str(last_user_message or "").strip().lower()
    assistant_text = str(assistant_message or "").strip().lower()
    if not user_text or not assistant_text:
        return None
    if any(keyword.lower() in user_text for keyword in CONVERSATION_END_KEYWORDS):
        return None
    if any(keyword.lower() in assistant_text for keyword in CONVERSATION_END_KEYWORDS):
        return None
    if "?" in assistant_text or "？" in assistant_text:
        return "assistant_question"
    if any(phrase.lower() in assistant_text for phrase in FOLLOW_UP_PHRASES):
        return "assistant_open_loop"
    if len(user_text) >= 8 and any(keyword.lower() in user_text for keyword in OPEN_TOPIC_KEYWORDS):
        return "user_open_topic"
    return None


def build_follow_up_instruction(
    activity: Dict[str, Any],
    now: datetime,
    follow_up_cfg: Dict[str, Any],
) -> str:
    """构建对话追踪指令。

    Args:
        activity: 目标的活跃状态字典
        now: 当前时间
        follow_up_cfg: follow_up 配置

    Returns:
        指令字符串，空字符串表示不需要追踪
    """
    if not follow_up_cfg.get("enabled", True):
        return ""

    due_at = activity.get("pending_follow_up_due_at")
    reference_at = activity.get("pending_follow_up_reference_at")
    last_user_at = activity.get("last_user_message_at")
    last_assistant_at = activity.get("last_assistant_message_at")
    if not due_at or not reference_at or not last_user_at or not last_assistant_at:
        return ""
    if now < due_at:
        return ""
    if last_user_at > last_assistant_at:
        return ""

    min_user_messages = _safe_int(follow_up_cfg.get("min_user_messages"), 1, minimum=1)
    if activity.get("total_user_messages", 0) < min_user_messages:
        return ""
    if activity.get("last_follow_up_sent_at") and activity["last_follow_up_sent_at"] >= reference_at:
        return ""

    silent_for = _humanize_gap(now - last_assistant_at)
    topic_summary = _shorten_text(activity.get("last_user_message") or "", 90)
    last_reply = _shorten_text(activity.get("last_assistant_message") or "", 120)
    custom_instruction = str(follow_up_cfg.get("instruction") or "").strip()
    parts = [
        custom_instruction or "请像真实伴侣一样，自然续上刚才没聊完的话题，用1-2句轻轻追一句，不要像系统提醒。",
        f"距离你上一句发出后，对方已经安静了大约 {silent_for}。",
    ]
    if topic_summary:
        parts.append(f"用户刚才提到：{topic_summary}")
    if last_reply:
        parts.append(f"你上一句大意：{last_reply}")
    parts.append("延续刚才的话题，不要重新开场，不要重复整段上下文，不要直接说\u201c检测到你没回复\u201d。")
    return "\n".join(parts)


def build_inactivity_instruction(
    activity: Dict[str, Any],
    now: datetime,
    inactive_cfg: Dict[str, Any],
) -> str:
    """构建不活跃问候指令。

    Args:
        activity: 目标的活跃状态字典
        now: 当前时间
        inactive_cfg: inactive_greeting 配置

    Returns:
        指令字符串，空字符串表示不需要问候
    """
    if not inactive_cfg.get("enabled", True):
        return ""

    last_user_at = activity.get("last_user_message_at")
    if not last_user_at:
        return ""

    min_user_messages = _safe_int(inactive_cfg.get("min_user_messages"), 1, minimum=1)
    if activity.get("total_user_messages", 0) < min_user_messages:
        return ""

    after_seconds = _safe_int(inactive_cfg.get("after_seconds"), 21600, minimum=60)
    if (now - last_user_at).total_seconds() < after_seconds:
        return ""
    if activity.get("inactivity_triggered_for_user_at") == last_user_at:
        return ""

    last_assistant_at = activity.get("last_assistant_message_at")
    if last_assistant_at and last_user_at > last_assistant_at:
        return ""

    silent_for = _humanize_gap(now - last_user_at)
    topic_summary = _shorten_text(activity.get("last_user_message") or "", 90)
    custom_instruction = str(inactive_cfg.get("instruction") or "").strip()
    parts = [
        custom_instruction or "请主动发一条自然的关心问候，像恋人想起对方时顺手发来的消息，语气轻松，不要太正式。",
        f"对方已经大约 {silent_for} 没来找你聊天了。",
    ]
    if topic_summary:
        parts.append(f"他上次提到过：{topic_summary}")
    parts.append("可以自然表达想念、关心近况或延续一点熟悉感，但不要显得催促，也不要说自己在执行规则。")
    return "\n".join(parts)


# ---- 工具函数 ----

def _safe_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _shorten_text(text: str, limit: int = 80) -> str:
    normalized = " ".join(str(text or "").strip().split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)] + "…"


def _humanize_gap(delta: timedelta) -> str:
    total_seconds = max(0, int(delta.total_seconds()))
    if total_seconds < 60:
        return f"{total_seconds} 秒"
    if total_seconds < 3600:
        return f"{max(1, total_seconds // 60)} 分钟"
    if total_seconds < 86400:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if minutes:
            return f"{hours} 小时 {minutes} 分钟"
        return f"{hours} 小时"
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    if hours:
        return f"{days} 天 {hours} 小时"
    return f"{days} 天"
