"""Personal edition authentication API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.requests import Request

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
