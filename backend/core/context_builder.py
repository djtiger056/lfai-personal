"""上下文构建器

负责将各种上下文源（记忆、MCP、companion hint 等）注入到 enhanced_history 中，
供 LLM 调用使用。从 bot.py 中提取，消除 chat/chat_stream/generate_proactive_reply 的重复代码。
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ..mcp import MCPManager
    from ..memory import MemoryManager


class ContextBuilder:
    """构建 LLM 调用所需的增强上下文（enhanced_history）。

    使用方式：
        builder = ContextBuilder(bot)
        enhanced = await builder.build(
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

    async def build(
        self,
        message: str,
        user_id: str,
        session_id: str,
        history: List[Dict[str, Any]],
        relevant_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """构建增强的对话历史。

        Args:
            message: 当前用户消息（或主动聊天的 instruction）
            user_id: 用户 ID
            session_id: 会话 ID
            history: 原始对话历史（不会被修改）
            relevant_memories: 已检索到的长期记忆列表

        Returns:
            增强后的对话历史（深拷贝，不影响原始 history）
        """
        enhanced_history = copy.deepcopy(history)

        # 1. 同类问题间隔较久时按"新一轮近况"处理
        long_gap_repeat_hint = self._bot._build_long_gap_repeat_hint(history, message)
        if long_gap_repeat_hint:
            self._inject_system_content(enhanced_history, long_gap_repeat_hint)

        # 2. 降低问答机器人感：按概率提示"主动分享一点自己的状态/关系感受"
        companion_hint = self._bot._build_companion_mode_hint(session_id, history, message)
        if companion_hint:
            self._inject_system_content(enhanced_history, companion_hint)

        # 3. 从 MCP 扩展收集自动上下文（例如当前时间）
        mcp_blocks = await self._collect_mcp_context(message)
        if mcp_blocks:
            mcp_context = "以下是 MCP 提供的实时上下文：\n" + "\n".join(
                f"- {block}" for block in mcp_blocks
            )
            self._inject_system_content(enhanced_history, mcp_context)

        # 4. 注入中期摘要上下文（可配置条数）
        await self._bot._append_mid_term_context(enhanced_history, user_id, session_id)

        # 5. 注入长期记忆上下文
        if relevant_memories:
            memory_context = self._bot._build_memory_context(relevant_memories, history, limit=3)
            if memory_context:
                self._inject_system_content(enhanced_history, memory_context)

        # 6. 添加当前用户消息
        enhanced_history.append({
            "role": "user",
            "content": message,
        })

        return enhanced_history

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

    @staticmethod
    def _inject_system_content(enhanced_history: List[Dict[str, Any]], content: str) -> None:
        """将内容追加到 system 消息中（如果存在），否则插入新的 system 消息。"""
        if enhanced_history and enhanced_history[0].get("role") == "system":
            enhanced_history[0]["content"] = enhanced_history[0]["content"] + "\n\n" + content
        else:
            enhanced_history.insert(0, {
                "role": "system",
                "content": content,
            })
