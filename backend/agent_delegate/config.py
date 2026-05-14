"""Agent 委派配置模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class HermesConfig:
    """Hermes Agent 连接配置"""

    api_base: str = "http://127.0.0.1:8642"
    api_key: str = ""
    timeout: int = 300  # 单次任务最大等待秒数
    poll_interval: float = 3.0  # 轮询间隔秒数
    max_concurrent_tasks: int = 5
    instructions: str = (
        "你是一个能干的助理。语气亲切自然，称呼用户\"你\"。\n"
        "任务结果该正式就正式（代码用代码块），但可以在开头结尾带一点温度。\n"
        "不要撒娇，不要用颜文字。简洁高效地完成任务。"
    )


@dataclass
class AgentDelegateConfig:
    """Agent 委派总配置"""

    enabled: bool = False
    hermes: HermesConfig = field(default_factory=HermesConfig)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "AgentDelegateConfig":
        """从字典构建配置"""
        if not data:
            return cls()

        hermes_data = data.get("hermes", {})
        hermes = HermesConfig(
            api_base=hermes_data.get("api_base", HermesConfig.api_base),
            api_key=hermes_data.get("api_key", HermesConfig.api_key),
            timeout=hermes_data.get("timeout", HermesConfig.timeout),
            poll_interval=hermes_data.get("poll_interval", HermesConfig.poll_interval),
            max_concurrent_tasks=hermes_data.get("max_concurrent_tasks", HermesConfig.max_concurrent_tasks),
            instructions=hermes_data.get("instructions", HermesConfig.instructions),
        )

        return cls(
            enabled=data.get("enabled", False),
            hermes=hermes,
        )
