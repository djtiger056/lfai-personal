"""主动聊天消息/指令构建器

负责构建发送给 Bot 的 instruction 文本。
从 ProactiveChatScheduler._build_instruction 中提取。
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional


def build_instruction(
    target: Dict[str, Any],
    window_cfg: Optional[Dict[str, Any]] = None,
    override_instruction: Optional[str] = None,
    default_prompt: str = "",
    global_templates: Optional[List[str]] = None,
) -> str:
    """构建主动聊天的 instruction。

    Args:
        target: 目标配置字典
        window_cfg: 时间窗口配置（可选）
        override_instruction: 覆盖指令（如手动触发时传入）
        default_prompt: 全局默认提示词
        global_templates: 全局消息模板列表

    Returns:
        构建好的 instruction 字符串
    """
    instruction = override_instruction or ""
    if not instruction:
        parts: List[str] = []
        if default_prompt:
            parts.append(default_prompt)
        else:
            parts.append(
                "请以恋爱中的女友身份，用2-3句轻松语气主动问候\u201c主人\u201d的近况，"
                "结合最近对话和所有记忆，表现关心又自然。"
            )
        if target.get("prompt"):
            parts.append(str(target["prompt"]))
        if window_cfg and window_cfg.get("prompt"):
            parts.append(str(window_cfg["prompt"]))
        instruction = "\n".join(parts)

    templates: List[str] = (
        (window_cfg.get("message_templates") if window_cfg else None)
        or target.get("message_templates")
        or global_templates
        or []
    )
    if templates:
        instruction = f"{instruction}\n可参考灵感：{random.choice(templates)}"

    return instruction
