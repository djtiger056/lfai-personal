"""Personal edition prompt APIs backed by data/personal/prompts."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.accounts import account_registry
from backend.config import config
from backend.api.bot_provider import get_bot
from backend.adapters.linyu_manager import get_linyu_session_manager
from backend.personal_auth import require_personal_auth
from backend.prompt_defaults import DEFAULT_ROLEPLAY_PROMPT
from backend.prompt_system.manager import prompt_manager
from backend.utils.companion_identity import (
    LEGACY_LINYU_COMPANION_PREFIX,
    companion_user_id,
    parse_companion_user_id,
)


router = APIRouter(prefix="/api/prompt", tags=["prompt_system"], dependencies=[Depends(require_personal_auth)])


class GetPromptResponse(BaseModel):
    content: str
    is_custom: bool
    updated_at: Optional[str] = None
    source: str = "config"
    companion_id: Optional[str] = None


class UpdatePromptRequest(BaseModel):
    content: str = Field(description="新的提示词内容")
    source: str = "user"
    summary: str = ""


class UpdatePromptResponse(BaseModel):
    success: bool
    content: str
    message: str = ""


class GetRulesResponse(BaseModel):
    content: str
    is_custom: bool


class UpdateRulesRequest(BaseModel):
    content: str
    source: str = "user"


def _roleplay_prompt() -> str:
    return str(config.get("roleplay_prompt", "") or DEFAULT_ROLEPLAY_PROMPT)


def _resolve_companion_prompt_id(raw_companion_id: Optional[str]) -> Optional[str]:
    """Return the canonical prompt identity used by runtime sessions."""
    raw = str(raw_companion_id or "").strip()
    if not raw:
        return None

    if raw.startswith(LEGACY_LINYU_COMPANION_PREFIX):
        legacy_value = raw[len(LEGACY_LINYU_COMPANION_PREFIX):]
        try:
            legacy_id = int(legacy_value)
        except Exception:
            raise HTTPException(status_code=400, detail="伴侣身份格式无效")
        companion_id = account_registry.resolve_legacy_linyu_ai_companion_id(legacy_id)
        if companion_id is None:
            raise HTTPException(status_code=404, detail="未找到对应的伴侣账号")
        return companion_user_id(companion_id)

    companion_pk = parse_companion_user_id(raw)
    if companion_pk is None:
        raise HTTPException(status_code=400, detail="伴侣身份格式无效")
    if not account_registry.get_companion(companion_pk, include_bindings=False, include_platform_accounts=False):
        raise HTTPException(status_code=404, detail="未找到对应的伴侣账号")
    return companion_user_id(companion_pk)


def _invalidate_companion_runtime(companion_id: str) -> None:
    """Make prompt edits visible to the already-running runtime."""
    prompt_manager.invalidate_cache(companion_id)
    try:
        bot = get_bot()
        bot.invalidate_user_cache(companion_id)
        memory_user_id, memory_session_id = bot._get_memory_scope(companion_id)
        bot._history_manager.get_session_history(
            memory_session_id,
            bot._get_user_system_prompt(memory_user_id),
        )
    except Exception:
        pass

    manager = get_linyu_session_manager()
    if manager:
        try:
            manager.request_refresh_user(companion_id)
        except Exception:
            pass


@router.get("", response_model=GetPromptResponse)
async def get_prompt(companion_id: Optional[str] = Query(default=None)):
    if companion_id:
        resolved_companion_id = _resolve_companion_prompt_id(companion_id)
        data = prompt_manager.get_prompt_data(resolved_companion_id)
        content = data.content or config.system_prompt or ""
        return GetPromptResponse(
            content=content,
            is_custom=bool(data.content),
            updated_at=data.updated_at,
            source=data.source if data.content else "default",
            companion_id=resolved_companion_id,
        )
    return GetPromptResponse(
        content=config.system_prompt or "",
        is_custom=bool(config.system_prompt),
        updated_at=config.get_prompt_updated_at("system_prompt"),
        source="file",
    )


@router.put("", response_model=UpdatePromptResponse)
async def update_prompt(request: UpdatePromptRequest, companion_id: Optional[str] = Query(default=None)):
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="提示词内容不能为空")
    if companion_id:
        resolved_companion_id = _resolve_companion_prompt_id(companion_id)
        ok = prompt_manager.set_prompt(
            resolved_companion_id,
            request.content.strip(),
            source=request.source or "user",
            summary=request.summary or "",
        )
        if not ok:
            raise HTTPException(status_code=500, detail="提示词保存失败")
        _invalidate_companion_runtime(resolved_companion_id)
        return UpdatePromptResponse(success=True, content=request.content.strip(), message="伴侣人设提示词已保存")
    config.update_config("system_prompt", request.content.strip())
    config.refresh_from_file()
    return UpdatePromptResponse(success=True, content=request.content.strip(), message="提示词已保存")


@router.delete("")
async def reset_prompt(companion_id: Optional[str] = Query(default=None)):
    if companion_id:
        resolved_companion_id = _resolve_companion_prompt_id(companion_id)
        if not prompt_manager.delete_prompt(resolved_companion_id):
            raise HTTPException(status_code=500, detail="提示词重置失败")
        _invalidate_companion_runtime(resolved_companion_id)
        return {"success": True, "message": "伴侣人设提示词已清空"}
    config.delete_prompt_value("system_prompt")
    config.refresh_from_file()
    return {"success": True, "message": "人设提示词已清空"}


@router.get("/history")
async def get_prompt_history(limit: int = 20, companion_id: Optional[str] = Query(default=None)):
    if companion_id:
        resolved_companion_id = _resolve_companion_prompt_id(companion_id)
        return {"records": [record.model_dump() for record in prompt_manager.get_history(resolved_companion_id, limit=limit).records]}
    return {"records": []}


@router.get("/default")
async def get_default_prompt():
    return {"content": config.system_prompt or "", "source": "file"}


@router.get("/rules", response_model=GetRulesResponse)
async def get_rules(companion_id: Optional[str] = Query(default=None)):
    if companion_id:
        resolved_companion_id = _resolve_companion_prompt_id(companion_id)
        content = prompt_manager.get_effective_rules(resolved_companion_id)
        return GetRulesResponse(content=content, is_custom=bool(prompt_manager.get_rules(resolved_companion_id)))
    return GetRulesResponse(content=config.system_rules or "", is_custom=bool(config.system_rules))


@router.put("/rules", response_model=UpdatePromptResponse)
async def update_rules(request: UpdateRulesRequest, companion_id: Optional[str] = Query(default=None)):
    if companion_id:
        resolved_companion_id = _resolve_companion_prompt_id(companion_id)
        ok = prompt_manager.set_rules(resolved_companion_id, request.content or "", source=request.source or "user")
        if not ok:
            raise HTTPException(status_code=500, detail="功能协议保存失败")
        _invalidate_companion_runtime(resolved_companion_id)
        return UpdatePromptResponse(success=True, content=request.content or "", message="伴侣功能协议已保存")
    config.update_config("system_rules", request.content or "")
    config.refresh_from_file()
    return UpdatePromptResponse(success=True, content=request.content or "", message="功能协议已保存")


@router.delete("/rules")
async def reset_rules(companion_id: Optional[str] = Query(default=None)):
    if companion_id:
        resolved_companion_id = _resolve_companion_prompt_id(companion_id)
        prompt_manager.delete_rules(resolved_companion_id)
        _invalidate_companion_runtime(resolved_companion_id)
        return {"success": True, "message": "伴侣功能协议已清空", "default_rules_preview": config.system_rules or ""}
    config.delete_prompt_value("system_rules")
    config.refresh_from_file()
    return {"success": True, "message": "功能协议已清空", "default_rules_preview": ""}


@router.get("/rules/default")
async def get_default_rules():
    return {"content": config.system_rules or "", "source": "file"}


@router.get("/roleplay", response_model=GetRulesResponse)
async def get_roleplay_prompt():
    content = _roleplay_prompt()
    return GetRulesResponse(content=content, is_custom=bool(config.get("roleplay_prompt", "")))


@router.put("/roleplay", response_model=UpdatePromptResponse)
async def update_roleplay_prompt(request: UpdateRulesRequest):
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="情景演绎提示词不能为空")
    config.update_config("roleplay_prompt", request.content.strip())
    config.refresh_from_file()
    return UpdatePromptResponse(success=True, content=request.content.strip(), message="情景演绎提示词已保存")


@router.delete("/roleplay")
async def reset_roleplay_prompt():
    config.delete_prompt_value("roleplay_prompt")
    config.refresh_from_file()
    return {"success": True, "message": "已重置为默认情景演绎提示词"}


@router.get("/roleplay/default")
async def get_default_roleplay_prompt():
    return {"content": DEFAULT_ROLEPLAY_PROMPT, "source": "builtin"}


@router.get("/roleplay/exit-summary/default")
async def get_default_roleplay_exit_summary_prompt():
    from backend.core.bot import DEFAULT_ROLEPLAY_EXIT_SUMMARY_PROMPT

    return {"content": DEFAULT_ROLEPLAY_EXIT_SUMMARY_PROMPT, "source": "builtin"}
