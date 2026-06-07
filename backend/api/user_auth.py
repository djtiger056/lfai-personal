"""Personal edition authentication API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.requests import Request

from backend.user import auth_manager, user_manager
from backend.config import config
from backend.personal_auth import (
    create_personal_token,
    get_ui_auth_config,
    request_is_authenticated,
    require_personal_auth,
    verify_credentials,
)


router = APIRouter(prefix="/api", tags=["auth"])


class VerifyRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = ""


class AuthSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    username: Optional[str] = None
    password: Optional[str] = None


async def _resolve_linyu_user_id(linyu_user_id: str) -> Optional[str]:
    """兼容旧绑定接口：账号名解析为 Linyu UUID。"""
    from fastapi import HTTPException
    from backend.api.accounts import _resolve_linyu_user_account

    token = str(linyu_user_id or "").strip()
    if not token:
        return None
    if len(token) == 36 and token.count("-") == 4:
        return token
    try:
        resolved = await _resolve_linyu_user_account(token)
    except HTTPException:
        return None
    return str(resolved.get("remote_user_id") or "").strip() or None


async def bind_linyu_account(*, token: str, linyu_user_id: str) -> Dict[str, Any]:
    """兼容旧测试/旧调用路径的 Linyu 绑定函数。"""
    from fastapi import HTTPException

    auth_user = auth_manager.get_user_from_token(token)
    if not auth_user or not auth_user.get("user_id"):
        raise HTTPException(status_code=401, detail="认证失效")

    user_id = int(auth_user["user_id"])
    user = await user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    raw_account = str(linyu_user_id or "").strip()
    resolved_user_id = await _resolve_linyu_user_id(raw_account)
    if not resolved_user_id:
        raise HTTPException(status_code=400, detail="未能解析 Linyu 账号")

    existing = await user_manager.get_user_by_linyu_id(resolved_user_id)
    if existing and int(getattr(existing, "id", 0) or 0) != user_id:
        raise HTTPException(status_code=400, detail="该 Linyu 账号已被其他用户绑定")

    updated = await user_manager.update_user(
        user_id=user_id,
        linyu_user_id=resolved_user_id,
        linyu_account=raw_account,
    )
    if not updated:
        raise HTTPException(status_code=500, detail="绑定 Linyu 账号失败")

    return {
        "user_id": user_id,
        "linyu_user_id": resolved_user_id,
        "linyu_account": raw_account,
    }


@router.get("/auth/status")
async def auth_status(request: Request):
    ui_cfg = get_ui_auth_config()
    return {
        "enabled": ui_cfg["enabled"],
        "authenticated": request_is_authenticated(request),
        "username": ui_cfg["username"],
    }


@router.post("/auth/verify")
async def verify(request: VerifyRequest):
    if not verify_credentials(request.username, request.password):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="账号或密码错误")
    return {
        "access_token": create_personal_token(request.username),
        "token_type": "bearer",
        "user": {
            "id": 1,
            "username": request.username,
            "nickname": "个人管理员",
            "is_admin": 1,
        },
    }


@router.post("/auth/logout")
async def logout():
    return {"success": True}


@router.get("/auth/settings", dependencies=[Depends(require_personal_auth)])
async def get_auth_settings():
    ui_cfg = get_ui_auth_config()
    return {
        "enabled": ui_cfg["enabled"],
        "username": ui_cfg["username"],
        "password": ui_cfg["password"],
    }


@router.put("/auth/settings", dependencies=[Depends(require_personal_auth)])
async def update_auth_settings(request: AuthSettingsRequest):
    current = get_ui_auth_config()
    next_cfg: Dict[str, Any] = {
        "enabled": current["enabled"] if request.enabled is None else request.enabled,
        "username": current["username"] if request.username is None else request.username,
        "password": current["password"] if request.password is None else request.password,
    }
    config.update_config("auth", {"ui_auth": next_cfg})
    config.refresh_from_file()
    return {
        "enabled": next_cfg["enabled"],
        "username": next_cfg["username"],
        "password": next_cfg["password"],
    }


@router.post("/auth/login")
async def login_compat(request: VerifyRequest):
    return await verify(request)


@router.get("/auth/me", dependencies=[Depends(require_personal_auth)])
async def me_compat():
    ui_cfg = get_ui_auth_config()
    return {
        "id": 1,
        "username": ui_cfg["username"],
        "nickname": "个人管理员",
        "qq_user_id": None,
        "linyu_user_id": None,
        "linyu_account": None,
        "avatar": None,
        "is_active": 1,
        "is_admin": 1,
        "created_at": "1970-01-01T00:00:00",
    }
