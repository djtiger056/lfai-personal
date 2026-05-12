import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.asr.config import ASRConfig
from backend.asr.manager import ASRManager
from backend.config import config as app_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["asr"])

_asr_manager: Optional[ASRManager] = None
bot_instance = None  # 由 main.py 启动时注入


class ASRConfigRequest(BaseModel):
    """ASR 配置请求体"""

    enabled: Optional[bool] = Field(None, description="是否开启语音识别")
    provider: Optional[str] = Field(None, description="ASR 提供商")
    siliconflow: Optional[Dict[str, Any]] = Field(None, description="硅基流动配置")
    qwen: Optional[Dict[str, Any]] = Field(None, description="千问配置")
    assemblyai: Optional[Dict[str, Any]] = Field(None, description="AssemblyAI配置")
    auto_send_to_llm: Optional[bool] = Field(None, description="是否自动把识别结果发给 LLM")
    processing_message: Optional[str] = Field(None, description="处理中的提示语")
    error_message: Optional[str] = Field(None, description="失败提示语")


def _get_asr_manager() -> ASRManager:
    """获取（或初始化）ASR 管理器实例"""
    global _asr_manager
    if _asr_manager is None:
        try:
            asr_config = app_config.asr_config
        except Exception as exc:
            logger.error("加载 ASR 配置失败，使用默认配置: %s", exc)
            asr_config = ASRConfig()
        _asr_manager = ASRManager(asr_config)
    return _asr_manager


@router.get("/asr/config")
async def get_asr_config():
    """获取 ASR 配置"""
    try:
        manager = _get_asr_manager()
        return {"success": True, "data": manager.config.dict()}
    except Exception as exc:
        logger.error("获取 ASR 配置失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"获取 ASR 配置失败: {exc}")


@router.post("/asr/config")
async def update_asr_config(config_request: ASRConfigRequest):
    """更新 ASR 配置并保存到文件"""
    try:
        update_data = config_request.dict(exclude_unset=True)

        # 通过统一的 Config 类更新并持久化
        app_config.update_config('asr', update_data)
        app_config.refresh_from_file()

        new_asr_config = app_config.asr_config

        # 更新 API 自己的 ASR manager
        manager = _get_asr_manager()
        manager.update_config(new_asr_config)

        # 同步更新 Bot 实例的 ASR manager（QQ 适配器等用的是 Bot 的）
        if bot_instance is not None and hasattr(bot_instance, 'asr_manager'):
            if bot_instance.asr_manager is not None:
                bot_instance.asr_manager.update_config(new_asr_config)
            else:
                bot_instance.asr_manager = ASRManager(new_asr_config)
            logger.info("Bot 实例的 ASR 配置已同步更新")

        return {"success": True, "message": "ASR 配置更新成功"}
    except Exception as exc:
        logger.error("更新 ASR 配置失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"更新 ASR 配置失败: {exc}")


@router.post("/asr/test")
async def test_asr_connection():
    """测试 ASR 连接有效性"""
    try:
        manager = _get_asr_manager()
        success = await manager.test_connection()
        return {
            "success": success,
            "message": "ASR 连接正常" if success else "ASR 连接测试失败",
        }
    except Exception as exc:
        logger.error("ASR 连接测试失败: %s", exc)
        return {"success": False, "message": f"ASR 连接测试失败: {exc}"}
