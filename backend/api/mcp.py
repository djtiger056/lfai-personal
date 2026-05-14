import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .bot_provider import get_bot

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class InstallPluginRequest(BaseModel):
    name: str
    pip_spec: str
    module: str
    class_name: str = "Plugin"
    description: Optional[str] = ""
    auto_context: bool = False
    meta: Dict[str, Any] = Field(default_factory=dict)


class ExecuteToolRequest(BaseModel):
    tool: str
    params: Dict[str, Any] = Field(default_factory=dict)


@router.get("/plugins")
async def list_plugins():
    """列出已加载的 MCP 插件及工具"""
    try:
        bot = get_bot()
        plugins = bot.mcp_manager.list_plugins()
        return {"plugins": plugins}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取插件列表失败: {str(e)}")


@router.post("/plugins/install")
async def install_plugin(request: InstallPluginRequest):
    """通过 pip 安装并注册一个 MCP 插件"""
    bot = get_bot()
    try:
        spec = bot.mcp_manager.install_plugin(
            name=request.name,
            pip_spec=request.pip_spec,
            module=request.module,
            class_name=request.class_name,
            description=request.description or "",
            auto_context=request.auto_context,
            meta=request.meta,
        )
        return {
            "installed": request.name,
            "spec": asdict(spec),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"安装插件失败: {str(e)}")


@router.post("/plugins/{plugin_name}/execute")
async def execute_tool(plugin_name: str, request: ExecuteToolRequest):
    """执行 MCP 插件暴露的工具"""
    bot = get_bot()
    try:
        result = await bot.run_mcp_tool(plugin_name, request.tool, request.params)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"执行插件失败: {str(e)}")
