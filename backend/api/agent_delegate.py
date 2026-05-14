"""Agent 委派配置 API"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from backend.api.bot_provider import get_bot
from backend.core.bot import Bot
from backend.config import config

router = APIRouter(prefix="/api/agent-delegate", tags=["Agent委派"])


class AgentDelegateConfigRequest(BaseModel):
    """Agent 委派配置请求"""
    enabled: bool = False
    hermes: Dict[str, Any] = {}


@router.get("/config")
async def get_agent_delegate_config():
    """获取 Agent 委派配置"""
    try:
        raw = config.get("agent_delegate", {})
        return {
            "success": True,
            "data": raw or {
                "enabled": False,
                "hermes": {
                    "api_base": "http://127.0.0.1:8642",
                    "api_key": "",
                    "timeout": 300,
                    "poll_interval": 3,
                    "max_concurrent_tasks": 5,
                    "instructions": "",
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_agent_delegate_config(request: AgentDelegateConfigRequest):
    """更新 Agent 委派配置"""
    try:
        config.update_config("agent_delegate", request.dict())
        return {
            "success": True,
            "message": "配置已保存，重启后生效"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_agent_delegate_status(bot: Bot = Depends(get_bot)):
    """获取 Agent 委派器运行状态"""
    try:
        delegator = bot.agent_delegator
        if not delegator:
            return {
                "success": True,
                "data": {
                    "initialized": False,
                    "enabled": False,
                    "active_tasks": 0,
                    "tasks": [],
                    "hermes_online": False,
                }
            }

        # 检查 Hermes 是否在线
        hermes_online = await delegator._client.health_check()

        return {
            "success": True,
            "data": {
                "initialized": True,
                "enabled": delegator.enabled,
                "active_tasks": delegator.active_task_count(),
                "tasks": delegator.active_tasks_snapshot(),
                "hermes_online": hermes_online,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-connection")
async def test_hermes_connection(bot: Bot = Depends(get_bot)):
    """测试 Hermes Agent 连接"""
    try:
        delegator = bot.agent_delegator
        if not delegator:
            return {
                "success": False,
                "message": "Agent 委派器未初始化，请先启用并重启服务"
            }

        online = await delegator._client.health_check()
        if online:
            return {
                "success": True,
                "message": "Hermes Agent 连接正常"
            }
        else:
            return {
                "success": False,
                "message": "无法连接到 Hermes Agent，请检查服务是否启动"
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"连接测试失败: {str(e)}"
        }
