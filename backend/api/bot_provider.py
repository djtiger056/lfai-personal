"""统一的 Bot 单例管理

所有 API 模块应从此处获取 Bot 实例，避免各自维护独立的全局变量。
"""

from __future__ import annotations

import json
from typing import Optional

from ..config import config

_bot_instance = None
_llm_signature = None


def _current_llm_signature() -> tuple:
    """生成当前 LLM 配置的签名，用于判断是否需要重建 Bot"""
    config.refresh_from_file()
    llm_cfg = config.llm_config
    provider = llm_cfg.get('provider')
    provider_cfg = llm_cfg.get(provider, {}) if isinstance(llm_cfg, dict) else {}

    return (
        provider,
        llm_cfg.get('model'),
        llm_cfg.get('api_base'),
        llm_cfg.get('api_key'),
        llm_cfg.get('temperature'),
        llm_cfg.get('max_tokens'),
        json.dumps(provider_cfg, sort_keys=True, ensure_ascii=False),
    )


def get_bot():
    """获取共享 Bot 实例；LLM 配置变化时自动重建。

    所有 API 模块统一使用此函数获取 Bot，确保全局只有一个实例。
    """
    global _bot_instance, _llm_signature
    signature = _current_llm_signature()
    if _bot_instance is None or _llm_signature != signature:
        from ..core.bot import Bot
        _bot_instance = Bot()
        _llm_signature = signature
    return _bot_instance


def reset_bot():
    """重置 Bot 实例，方便在配置变更后重新创建。"""
    global _bot_instance, _llm_signature
    _bot_instance = None
    _llm_signature = None


def set_bot(bot) -> None:
    """由 main.py 启动时注入已创建的 Bot 实例。"""
    global _bot_instance, _llm_signature
    _bot_instance = bot
    _llm_signature = _current_llm_signature()
