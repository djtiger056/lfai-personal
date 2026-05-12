"""会话历史管理器

负责对话历史的增删改查、持久化恢复、trim 等操作。
从 bot.py 中提取，降低 Bot 类的复杂度。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from ..utils.datetime_utils import get_now


class HistoryManager:
    """管理多会话的对话历史。

    职责：
    - 获取/初始化指定会话的对话历史
    - 保持历史在配置上限内（trim）
    - 从持久化存储恢复历史（避免重启丢失上下文）
    - 清空历史
    """

    def __init__(self):
        self.session_histories: Dict[str, List[Dict[str, str]]] = {}
        self._history_loaded_sessions: Set[str] = set()

    def get_session_history(
        self,
        session_id: str,
        system_prompt: str = "",
    ) -> List[Dict[str, str]]:
        """获取或初始化指定会话的对话历史。

        Args:
            session_id: 会话 ID
            system_prompt: 当前生效的系统提示词（支持运行时修改）

        Returns:
            该会话的对话历史列表（引用，可直接 append）
        """
        history = self.session_histories.get(session_id)
        if history is None:
            history = []
            self.session_histories[session_id] = history

        # 确保 system prompt 与当前配置一致
        if system_prompt:
            if history and history[0].get("role") == "system":
                history[0]["content"] = system_prompt
            else:
                history.insert(0, {"role": "system", "content": system_prompt})
        return history

    def trim(self, session_id: str, limit: int, system_prompt: str = "") -> None:
        """保持对话历史在配置上限内。

        Args:
            session_id: 会话 ID
            limit: 最大消息条数
            system_prompt: 当前系统提示词
        """
        history = self.get_session_history(session_id, system_prompt)
        if len(history) > limit:
            if history and history[0].get("role") == "system":
                self.session_histories[session_id] = [history[0]] + history[-(limit - 1):]
            else:
                self.session_histories[session_id] = history[-limit:]

    async def load_from_memory(
        self,
        user_id: str,
        session_id: str,
        memory_manager,
        system_prompt: str = "",
        limit: int = 20,
    ) -> None:
        """从持久化存储中恢复短期对话历史。

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            memory_manager: 已初始化的 MemoryManager 实例
            system_prompt: 系统提示词
            limit: 恢复的最大消息条数
        """
        if session_id in self._history_loaded_sessions:
            return

        try:
            memories = await memory_manager.get_short_term_memories(
                user_id=user_id,
                session_id=session_id,
                limit=limit,
            )
        except Exception as e:
            print(f"[DEBUG] 恢复历史时获取短期记忆失败: {e}")
            return

        restored_history: List[Dict[str, Any]] = []
        for mem in memories:
            message = mem.get("message") or {}
            role = message.get("role")
            content = message.get("content")
            if role and content:
                restored_message: Dict[str, Any] = {"role": role, "content": content}
                message_ts = message.get("timestamp")
                if message_ts:
                    restored_message["timestamp"] = message_ts
                restored_history.append(restored_message)

        if restored_history:
            base_history: List[Dict[str, str]] = []
            if system_prompt:
                base_history.append({"role": "system", "content": system_prompt})
            self.session_histories[session_id] = base_history + restored_history
            try:
                state = await memory_manager._get_session_state(session_id, user_id)
                state["round_count"] = len(restored_history)
                state["updated_at"] = get_now().isoformat()
            except Exception as e:
                print(f"[DEBUG] 恢复记忆时更新会话状态失败: {e}")

        self._history_loaded_sessions.add(session_id)

    def clear(self, session_id: str, system_prompt: str = "") -> None:
        """清空指定会话的对话历史。

        Args:
            session_id: 会话 ID
            system_prompt: 清空后保留的系统提示词
        """
        history = self.get_session_history(session_id, "")
        history.clear()
        if system_prompt:
            history.append({"role": "system", "content": system_prompt})

    def get_copy(self, session_id: str, system_prompt: str = "") -> List[Dict[str, str]]:
        """获取指定会话对话历史的副本。"""
        return self.get_session_history(session_id, system_prompt).copy()
