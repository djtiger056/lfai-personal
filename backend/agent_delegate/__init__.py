"""Agent 委派模块 — 将任务委派给本地 Hermes Agent 执行"""

from .delegator import AgentDelegator
from .parser import extract_delegate_tag
from .client import HermesClient

__all__ = ["AgentDelegator", "extract_delegate_tag", "HermesClient"]
