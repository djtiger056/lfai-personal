from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.api.bot_provider import get_bot
from backend.personal_auth import require_personal_auth
from backend.utils.companion_identity import parse_companion_user_id


router = APIRouter(prefix="/api/companion-actions", tags=["companion-actions"], dependencies=[Depends(require_personal_auth)])


class CompanionActionsConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    autonomy_mode: Optional[str] = Field(default=None, pattern="^auto$")
    target_scope: Optional[str] = Field(default=None, pattern="^bound_and_friends$")
    allow_actions: Optional[list[str]] = None
    rate_limits: Optional[Dict[str, int]] = None


def _resolve_companion_id(raw_companion_id: Optional[str]) -> str:
    companion_id = str(raw_companion_id or "").strip()
    if parse_companion_user_id(companion_id) is None:
        raise HTTPException(status_code=400, detail="伴侣身份格式无效")
    return companion_id


@router.get("/catalog")
async def get_catalog(companion_id: Optional[str] = Query(default=None), bot=Depends(get_bot)):
    if companion_id is not None:
        _resolve_companion_id(companion_id)
    return {"catalog": bot.companion_action_manager.get_catalog()}


@router.get("/config")
async def get_config(companion_id: str = Query(...), bot=Depends(get_bot)):
    resolved = _resolve_companion_id(companion_id)
    try:
        return {"config": bot.companion_action_manager.get_config(resolved)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/config")
async def update_config(request: CompanionActionsConfigRequest, companion_id: str = Query(...), bot=Depends(get_bot)):
    resolved = _resolve_companion_id(companion_id)
    payload = {key: value for key, value in request.model_dump(exclude_none=True).items()}
    try:
        updated = bot.companion_action_manager.update_config(resolved, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "伴侣自主 IM 动作配置已保存", "config": updated}


@router.get("/logs")
async def list_logs(
    companion_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    bot=Depends(get_bot),
):
    resolved = _resolve_companion_id(companion_id)
    try:
        return {"logs": bot.companion_action_manager.list_logs(resolved, limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
