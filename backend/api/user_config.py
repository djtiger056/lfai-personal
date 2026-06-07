"""Personal-edition compatibility API for legacy /user/config callers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.bot_provider import reset_bot
from backend.adapters.linyu_manager import get_linyu_session_manager
from backend.config import config
from backend.personal_auth import require_personal_auth


router = APIRouter(prefix="/api", tags=["user_config"], dependencies=[Depends(require_personal_auth)])


class UserConfigResponse(BaseModel):
    """Compatibility shape used by older frontend pages.

    In the personal edition these fields are backed by data/personal/config.yaml
    plus data/personal/prompts/*.md, not by per-web-user override files.
    """

    system_prompt: Optional[str] = None
    llm: Optional[Dict[str, Any]] = None
    tts: Optional[Dict[str, Any]] = None
    asr: Optional[Dict[str, Any]] = None
    image_generation: Optional[Dict[str, Any]] = None
    video_generation: Optional[Dict[str, Any]] = None
    vision: Optional[Dict[str, Any]] = None
    prompt_enhancer: Optional[Dict[str, Any]] = None
    emotes: Optional[Dict[str, Any]] = None
    proactive_chat: Optional[Dict[str, Any]] = None
    adapters: Optional[Dict[str, Any]] = None
    agent_delegate: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None


class UpdateUserConfigRequest(BaseModel):
    system_prompt: Optional[str] = Field(default=None, description="已弃用，改用伴侣人格设定页面")
    llm: Optional[Dict[str, Any]] = Field(default=None, description="LLM配置")
    tts: Optional[Dict[str, Any]] = Field(default=None, description="TTS配置")
    asr: Optional[Dict[str, Any]] = Field(default=None, description="ASR配置")
    image_generation: Optional[Dict[str, Any]] = Field(default=None, description="图像生成配置")
    video_generation: Optional[Dict[str, Any]] = Field(default=None, description="视频生成配置")
    vision: Optional[Dict[str, Any]] = Field(default=None, description="视觉识别配置")
    prompt_enhancer: Optional[Dict[str, Any]] = Field(default=None, description="提示词增强配置")
    emotes: Optional[Dict[str, Any]] = Field(default=None, description="表情包配置")
    proactive_chat: Optional[Dict[str, Any]] = Field(default=None, description="主动消息配置")
    adapters: Optional[Dict[str, Any]] = Field(default=None, description="适配器配置")
    agent_delegate: Optional[Dict[str, Any]] = Field(default=None, description="Agent委派配置")
    preferences: Optional[Dict[str, Any]] = Field(default=None, description="个人版偏好设置")


_CONFIG_FIELDS = {
    "llm",
    "tts",
    "asr",
    "image_generation",
    "video_generation",
    "vision",
    "prompt_enhancer",
    "emotes",
    "proactive_chat",
    "adapters",
    "agent_delegate",
    "preferences",
}


def _current_config_response() -> UserConfigResponse:
    payload = {field: config.get(field, None) for field in _CONFIG_FIELDS}
    payload["system_prompt"] = None
    return UserConfigResponse(**payload)


def _refresh_runtime() -> None:
    config.refresh_from_file()
    reset_bot()
    manager = get_linyu_session_manager()
    if manager:
        manager.request_refresh_all()


@router.get("/user/config", response_model=UserConfigResponse)
async def get_user_config():
    """Return the single personal config using the legacy user-config shape."""

    return _current_config_response()


@router.put("/user/config", response_model=UserConfigResponse)
async def update_user_config(request: UpdateUserConfigRequest):
    """Update the single personal config through the legacy user-config endpoint."""

    update_data = request.dict(exclude_unset=True)
    for key, value in update_data.items():
        if key == "system_prompt":
            continue
        if key in _CONFIG_FIELDS and value is not None:
            config.update_config(key, value)

    _refresh_runtime()
    return _current_config_response()


@router.delete("/user/config")
async def reset_user_config(config_type: Optional[str] = None):
    """Clear compatible personal-edition config fields.

    This exists so older reset buttons do not fail, but the personal edition
    has no per-user override to restore.
    """

    if config_type:
        if config_type in _CONFIG_FIELDS:
            config.update_config(config_type, {})
            _refresh_runtime()
        return {"message": "配置已重置"}

    config.update_config("preferences", {})
    _refresh_runtime()
    return {"message": "配置已重置"}


@router.get("/user/profile", response_model=Dict[str, Any])
async def get_user_profile():
    return {
        "id": 1,
        "username": "admin",
        "nickname": "个人管理员",
        "qq_user_id": None,
        "avatar": None,
        "is_active": True,
        "is_admin": 1,
        "config": _current_config_response().dict(),
    }
