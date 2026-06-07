"""上下文构建器

负责收集对话所需的动态上下文，并将其整理为结构化 blocks。
这些 blocks 会交给 Prompt Assembly 层统一渲染成更清晰、稳定、缓存友好的 prompt。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..prompt_assembly import PromptBlock
from ..utils.datetime_utils import get_now, from_isoformat

if TYPE_CHECKING:
    from ..mcp import MCPManager
    from ..memory import MemoryManager


# ---- 时间段映射工具 ----

def _get_time_period(dt: datetime) -> str:
    """将时间映射到自然语言时段。"""
    hour = dt.hour
    if hour < 6:
        return "凌晨"
    elif hour < 9:
        return "早上"
    elif hour < 12:
        return "上午"
    elif hour < 14:
        return "中午"
    elif hour < 17:
        return "下午"
    elif hour < 19:
        return "傍晚"
    elif hour < 22:
        return "晚上"
    else:
        return "深夜"


def _format_relative_date(past: datetime, now: datetime) -> str:
    """生成相对日期描述。"""
    diff_days = (now.date() - past.date()).days
    if diff_days == 0:
        return "今天"
    elif diff_days == 1:
        return "昨天"
    elif diff_days == 2:
        return "前天"
    elif diff_days <= 7:
        return f"{diff_days}天前"
    else:
        return past.strftime("%m月%d日")


class ContextBuilder:
    """构建 LLM 调用所需的动态上下文 blocks。

    使用方式：
        builder = ContextBuilder(bot)
        snapshot = await builder.build(
            message=message,
            user_id=user_id,
            session_id=session_id,
            history=history,
            relevant_memories=relevant_memories,
        )
    """

    def __init__(self, bot):
        """
        Args:
            bot: Bot 实例，用于访问 mcp_manager、memory_manager 及各种 hint 方法。
        """
        self._bot = bot

    @dataclass
    class BuildResult:
        history_messages: List[Dict[str, Any]] = field(default_factory=list)
        dynamic_blocks: List[PromptBlock] = field(default_factory=list)
        message: str = ""
        user_id: str = ""
        session_id: str = ""

    async def build(
        self,
        message: str,
        user_id: str,
        session_id: str,
        history: List[Dict[str, Any]],
        relevant_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> "ContextBuilder.BuildResult":
        """构建结构化动态上下文。

        Args:
            message: 当前用户消息（或主动聊天的 instruction）
            user_id: 用户 ID
            session_id: 会话 ID
            history: 原始对话历史
            relevant_memories: 已检索到的长期记忆列表

        Returns:
            含历史消息和动态 blocks 的结果对象
        """
        history_messages = self._clone_history_with_time_markers(history)
        dynamic_blocks: List[PromptBlock] = []

        time_continuity_hint = self._build_time_continuity_hint(history)
        if time_continuity_hint:
            dynamic_blocks.append(self._make_context_block("time_continuity", "时间连续性", time_continuity_hint))

        long_gap_repeat_hint = self._bot._build_long_gap_repeat_hint(history, message)
        if long_gap_repeat_hint:
            dynamic_blocks.append(self._make_context_block("long_gap_repeat", "回答方式提醒", long_gap_repeat_hint))

        companion_hint = self._bot._build_companion_mode_hint(session_id, history, message)
        if companion_hint:
            dynamic_blocks.append(self._make_context_block("companion_hint", "关系表达提醒", companion_hint))

        mcp_blocks = await self._collect_mcp_context(message)
        if mcp_blocks:
            dynamic_blocks.append(self._make_context_block("mcp_context", "实时上下文", "\n".join(f"- {block}" for block in mcp_blocks)))

        mid_term_context = await self._bot._collect_mid_term_context(user_id, session_id)
        if mid_term_context:
            dynamic_blocks.append(self._make_context_block("mid_term_summary", "中期回顾", mid_term_context))

        if relevant_memories:
            memory_context = self._bot._build_memory_context(relevant_memories, history, limit=3)
            if memory_context:
                dynamic_blocks.append(self._make_context_block("long_term_memory", "长期记忆", memory_context))

        video_generation_hint = self._bot._build_video_generation_hint(user_id, session_id, message)
        if video_generation_hint:
            dynamic_blocks.append(self._make_context_block("video_generation_hint", "临时任务提示", video_generation_hint))

        return ContextBuilder.BuildResult(
            history_messages=history_messages,
            dynamic_blocks=dynamic_blocks,
            message=str(message or ""),
            user_id=str(user_id or ""),
            session_id=str(session_id or ""),
        )

    # ── 第一层：对话间隔感知 ──────────────────────────────────────────────────

    def _build_time_continuity_hint(self, history: List[Dict[str, Any]]) -> str:
        """构建时间连续性感知提示。

        让 AI 知道：
        1. 距离上次对话过了多久
        2. 期间经历了哪些时间段变化（如从上午到下午、跨天）
        3. 上次对话结束时的情境
        """
        now = get_now()

        # 从历史中找到最后一条用户消息和最后一条助手消息的时间戳
        last_user_ts: Optional[datetime] = None
        last_user_content: str = ""
        last_assistant_content: str = ""

        for item in reversed(history):
            role = item.get("role")
            if role == "user" and last_user_ts is None:
                ts = self._parse_timestamp(item)
                if ts:
                    last_user_ts = ts
                    last_user_content = str(item.get("content", "") or "").strip()[:100]
            elif role == "assistant" and not last_assistant_content:
                last_assistant_content = str(item.get("content", "") or "").strip()[:100]
            if last_user_ts and last_assistant_content:
                break

        if not last_user_ts:
            return ""

        gap = now - last_user_ts
        gap_seconds = gap.total_seconds()
        gap_minutes = int(gap_seconds / 60)

        # 短间隔（<5分钟）不需要提示，对话还在连续进行中
        if gap_minutes < 5:
            return ""

        parts: List[str] = []

        # 时间间隔的自然语言描述
        if gap_minutes < 60:
            time_desc = f"约{gap_minutes}分钟"
        elif gap_minutes < 1440:
            hours = gap_minutes // 60
            mins = gap_minutes % 60
            if mins > 10:
                time_desc = f"约{hours}小时{mins}分钟"
            else:
                time_desc = f"约{hours}小时"
        else:
            days = gap_minutes // 1440
            remaining_hours = (gap_minutes % 1440) // 60
            if remaining_hours > 0:
                time_desc = f"约{days}天{remaining_hours}小时"
            else:
                time_desc = f"约{days}天"

        parts.append(f"【时间感知】距离上次对话已过去{time_desc}。")

        # 时段变化感知
        last_period = _get_time_period(last_user_ts)
        current_period = _get_time_period(now)

        if last_user_ts.date() != now.date():
            # 跨天
            relative_date = _format_relative_date(last_user_ts, now)
            parts.append(f"上次聊天是{relative_date}的{last_period}，现在是{current_period}。")
        elif last_period != current_period:
            # 同天但跨时段
            parts.append(f"上次聊天还是{last_period}，现在已经是{current_period}了。")

        # 上次对话尾巴的情境（帮助 AI 自然衔接，仅在间隔>30分钟时提供）
        if gap_minutes > 30:
            if last_user_content:
                parts.append(f"对方上次说的是：「{last_user_content}」")
            if last_assistant_content:
                parts.append(f"你上次回复的是：「{last_assistant_content}」")

        # 行为指引（根据间隔长度给出不同的语气建议）
        if gap_minutes >= 1440:  # 1天以上
            parts.append(
                "已经隔了很久没聊，回复时自然表达想念或关心，"
                "可以问问对方这段时间过得怎么样，不要像刚才还在聊一样。"
            )
        elif gap_minutes >= 360:  # 6小时以上
            parts.append(
                "间隔较长，回复时可以自然带一句'好久没聊'的感觉，"
                "关心一下对方这段时间在做什么，语气温暖但不要太夸张。"
            )
        elif gap_minutes >= 60:  # 1小时以上
            parts.append(
                "有一段时间没聊了，回复时自然过渡，"
                "不要像刚才还在聊一样，可以轻轻带过时间感。"
            )
        elif gap_minutes >= 15:  # 15分钟以上
            parts.append(
                "间隔不算长但也不是连续对话，自然延续之前的氛围即可，"
                "不需要特别提时间但也不要完全忽略间隔。"
            )
        else:
            # 5-15分钟，轻微间隔
            parts.append("短暂间隔，自然延续对话即可。")

        return "\n".join(parts)

    # ── 第二层：历史消息时间标记 ──────────────────────────────────────────────

    def _inject_time_markers(self, enhanced_history: List[Dict[str, Any]]) -> None:
        """在间隔较大的历史消息之间插入时间标记。

        让 LLM 能"看到"对话中的时间流逝，而不是把所有历史消息当作连续发生的。
        仅在间隔 > 30 分钟的用户消息前插入时间分隔标记。
        """
        # 收集所有非 system 消息的索引和时间戳
        message_timestamps: List[tuple] = []  # (index, timestamp, role)
        for i, msg in enumerate(enhanced_history):
            role = msg.get("role", "")
            if role == "system":
                continue
            ts = self._parse_timestamp(msg)
            if ts:
                message_timestamps.append((i, ts, role))

        if len(message_timestamps) < 2:
            return

        # 从后往前遍历，找到需要插入时间标记的位置
        insertions: List[tuple] = []  # (index, marker_text)
        prev_ts: Optional[datetime] = None

        for idx, (msg_idx, ts, role) in enumerate(message_timestamps):
            if prev_ts is not None and role == "user":
                gap_minutes = (ts - prev_ts).total_seconds() / 60
                if gap_minutes >= 30:
                    period = _get_time_period(ts)
                    time_str = ts.strftime("%H:%M")

                    if gap_minutes >= 1440:
                        date_str = ts.strftime("%m/%d")
                        marker = f"—— {date_str} {period} {time_str} ——"
                    else:
                        marker = f"—— {period} {time_str} ——"

                    insertions.append((msg_idx, marker))
            prev_ts = ts

        # 从后往前插入标记（避免索引偏移）
        for msg_idx, marker in reversed(insertions):
            original_content = str(enhanced_history[msg_idx].get("content", "") or "")
            enhanced_history[msg_idx]["content"] = f"{marker}\n{original_content}"

    def _clone_history_with_time_markers(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cloned = [
            dict(item)
            for item in history
            if str(item.get("role", "") or "").strip() in {"user", "assistant"}
        ]
        self._inject_time_markers(cloned)
        return cloned

    @staticmethod
    def _make_context_block(block_id: str, title: str, content: str) -> PromptBlock:
        return PromptBlock(
            id=block_id,
            role="user",
            layer="context",
            stability="turn",
            title=title,
            content=str(content or ""),
        )

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_timestamp(message: Dict[str, Any]) -> Optional[datetime]:
        """从消息中解析时间戳。"""
        raw_ts = message.get("timestamp")
        if not raw_ts:
            return None
        if isinstance(raw_ts, datetime):
            return raw_ts
        if isinstance(raw_ts, str):
            try:
                return from_isoformat(raw_ts)
            except Exception:
                return None
        return None

    async def _collect_mcp_context(self, message: str) -> List[str]:
        """收集 MCP 自动上下文。"""
        mcp_manager: Optional[MCPManager] = getattr(self._bot, "mcp_manager", None)
        if not mcp_manager:
            return []
        try:
            return await mcp_manager.collect_auto_context(message)
        except Exception as e:
            print(f"[DEBUG] 检索 MCP 自动上下文失败: {e}")
            return []
