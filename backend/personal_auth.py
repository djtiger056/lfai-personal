"""Personal edition UI authentication.

All files in this project must be read/written as UTF-8.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException, Request, status

from backend.config import config
from backend.jwt_secret import get_jwt_secret_key
from backend.utils.datetime_utils import get_now


ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7


def get_ui_auth_config() -> Dict[str, Any]:
    auth_cfg = config.get("auth", {}) or {}
    ui_cfg = auth_cfg.get("ui_auth", {}) or {}
    return {
        "enabled": bool(ui_cfg.get("enabled", True)),
        "username": str(ui_cfg.get("username", "admin") or "admin"),
        "password": str(ui_cfg.get("password", "admin") or "admin"),
    }


def is_ui_auth_enabled() -> bool:
    return bool(get_ui_auth_config().get("enabled", True))


def _secret_key() -> str:
    return get_jwt_secret_key()


def create_personal_token(username: str) -> str:
    now = get_now()
    payload = {
        "sub": "personal-admin",
        "username": username,
        "scope": "personal_admin",
        "exp": now + timedelta(hours=TOKEN_EXPIRE_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def decode_personal_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    if payload.get("scope") != "personal_admin":
        return None
    return payload


def verify_credentials(username: str, password: str) -> bool:
    ui_cfg = get_ui_auth_config()
    return username == ui_cfg["username"] and password == ui_cfg["password"]


def extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        return request.query_params.get("token", "")
    parts = auth_header.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""


def request_is_authenticated(request: Request) -> bool:
    if not is_ui_auth_enabled():
        return True
    token = extract_bearer_token(request)
    return bool(token and decode_personal_token(token))


async def require_personal_auth(request: Request) -> None:
    if request_is_authenticated(request):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未通过身份验证")
