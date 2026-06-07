from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import yaml
import logging
from ..config import config
from ..utils.config_sanitizer import sanitize_adapters_config
from .bot_provider import reset_bot
from ..adapters.linyu_manager import get_linyu_session_manager
from backend.personal_auth import require_personal_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["config"])
CONFIG_PATH = config.config_path

class ConfigRequest(BaseModel):
    llm: Optional[Dict[str, Any]] = Field(None, description="LLM配置")
    adapters: Optional[Dict[str, Any]] = Field(None, description="适配器配置")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    system_rules: Optional[str] = Field(None, description="功能协议")
    roleplay_prompt: Optional[str] = Field(None, description="情景演绎提示词")
    preferences: Optional[Dict[str, Any]] = Field(None, description="个人版偏好设置")
    daily_schedule_generation: Optional[Dict[str, Any]] = Field(None, description="每日作息生成配置")
    tts: Optional[Dict[str, Any]] = Field(None, description="TTS配置")
    asr: Optional[Dict[str, Any]] = Field(None, description="ASR配置")
    image_generation: Optional[Dict[str, Any]] = Field(None, description="图像生成配置")
    video_generation: Optional[Dict[str, Any]] = Field(None, description="视频生成配置")
    vision: Optional[Dict[str, Any]] = Field(None, description="视觉识别配置")
    prompt_enhancer: Optional[Dict[str, Any]] = Field(None, description="提示词增强配置")
    emotes: Optional[Dict[str, Any]] = Field(None, description="表情包配置")
    agent_delegate: Optional[Dict[str, Any]] = Field(None, description="Agent委派配置")
    proactive_chat: Optional[Dict[str, Any]] = Field(None, description="主动消息配置")

@router.get("/config", dependencies=[Depends(require_personal_auth)])
async def get_config():
    """获取系统配置"""
    try:
        return config.as_dict(include_prompts=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配置失败: {str(e)}")

@router.post("/config", dependencies=[Depends(require_personal_auth)])
async def update_config(config_data: ConfigRequest):
    """更新系统配置"""
    try:
        # 读取现有配置
        existing_config = config.as_dict(include_prompts=False)
        
        # 只更新提供的字段
        update_data = config_data.dict(exclude_unset=True)
        logger.info(f"Received config update request with fields: {list(update_data.keys())}")
        
        for key, value in update_data.items():
            if value is not None:
                if key in {"system_prompt", "system_rules", "roleplay_prompt"}:
                    config.update_config(key, value)
                else:
                    if key == "adapters":
                        value = sanitize_adapters_config(value)
                    existing_config[key] = value
        
        # 保存配置
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(existing_config, f, default_flow_style=False, allow_unicode=True)

        # 热更新内存中的配置并重置Bot实例
        config.refresh_from_file()
        reset_bot()
        manager = get_linyu_session_manager()
        if manager:
            manager.request_refresh_all()
        
        logger.info("Config saved successfully")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to save config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")

@router.post("/test-llm")
async def test_llm():
    """测试LLM连接"""
    try:
        from ..core.bot import Bot
        bot = Bot()
        success = await bot.test_connection()
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}
