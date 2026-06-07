"""Personal edition external account APIs."""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional

import aiohttp
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.accounts import account_registry
from backend.adapters.linyu_manager import get_linyu_session_manager
from backend.config import config
from backend.personal_auth import require_personal_auth


router = APIRouter(prefix="/api", tags=["accounts"], dependencies=[Depends(require_personal_auth)])


class AccountRequest(BaseModel):
    platform: str = Field(pattern="^(qq|linyu)$")
    account_name: Optional[str] = Field(default=None, min_length=1)
    remote_user_id: Optional[str] = None
    display_name: str = ""
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AccountUpdateRequest(BaseModel):
    platform: Optional[str] = Field(default=None, pattern="^(qq|linyu)$")
    account_name: Optional[str] = None
    remote_user_id: Optional[str] = None
    display_name: Optional[str] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class CompanionPlatformAccountRequest(BaseModel):
    platform: str = Field(pattern="^(qq|linyu)$")
    account_name: str = Field(min_length=1)
    password: str = ""
    remote_user_id: Optional[str] = None
    enabled: bool = True
    is_primary: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompanionRequest(BaseModel):
    companion_name: str = ""
    platform_accounts: List[CompanionPlatformAccountRequest] = Field(default_factory=list)
    bound_account_ids: List[int] = Field(default_factory=list)
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompanionUpdateRequest(BaseModel):
    companion_name: Optional[str] = None
    platform_accounts: Optional[List[CompanionPlatformAccountRequest]] = None
    bound_account_ids: Optional[List[int]] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class BindingRequest(BaseModel):
    user_account_ids: List[int] = Field(default_factory=list)


class ResolveAccountRequest(BaseModel):
    account_name: str = Field(min_length=1)


class LinyuAccountResolver:
    def __init__(self, linyu_cfg: Dict[str, Any]):
        self.cfg = linyu_cfg or {}
        self.http_host = self.cfg.get("http_host", "127.0.0.1")
        self.http_port = self.cfg.get("http_port", 9200)
        self.http_timeout = float((self.cfg.get("reconnect_config") or {}).get("http_timeout", 15.0))
        self._base_url = self._build_http_base()

    def _build_http_base(self) -> str:
        host = str(self.http_host or "").strip().rstrip("/") or "127.0.0.1"
        if host.startswith(("http://", "https://")):
            base = host
        else:
            base = f"http://{host}"
        if not self._has_port(base):
            base = f"{base}:{self.http_port}"
        return base

    @staticmethod
    def _has_port(url: str) -> bool:
        netloc = url.split("://", 1)[1] if "://" in url else url
        return ":" in netloc

    async def _request_json(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
    ) -> Any:
        headers = {"x-token": token} if token else {}
        async with session.request(method, f"{self._base_url}{path}", json=json_data, headers=headers) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = text
            if resp.status >= 400:
                raise RuntimeError(f"Linyu API HTTP {resp.status}: {text[:160]}")
            return data

    @staticmethod
    def _encrypt_password(password: str, public_key_pem: str) -> str:
        public_key = load_pem_public_key(str(public_key_pem or "").encode("utf-8"))
        encrypted = public_key.encrypt(str(password or "").encode("utf-8"), padding.PKCS1v15())
        return base64.b64encode(encrypted).decode("utf-8")

    async def login(self, account_name: str, password: str) -> Dict[str, str]:
        if not account_name or not password:
            raise RuntimeError("缺少 Linyu 登录账号或密码")
        timeout = aiohttp.ClientTimeout(total=self.http_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            key_result = await self._request_json(session, "GET", "/v1/api/login/public-key")
            public_key = key_result.get("data") if isinstance(key_result, dict) else key_result
            encrypted_password = self._encrypt_password(password, str(public_key or ""))
            result = await self._request_json(
                session,
                "POST",
                "/v1/api/login",
                json_data={
                    "account": account_name,
                    "password": encrypted_password,
                    "onlineEquipment": "bot",
                },
            )
            data = result.get("data") if isinstance(result, dict) else None
            if not isinstance(data, dict) or not data.get("token"):
                raise RuntimeError(f"Linyu 登录失败: {result}")
            return {
                "token": str(data.get("token") or ""),
                "remote_user_id": str(data.get("userId") or ""),
            }

    async def resolve_user_by_account_name(
        self,
        account_name: str,
        login_account: str,
        password: str,
    ) -> Dict[str, str]:
        login = await self.login(login_account, password)
        timeout = aiohttp.ClientTimeout(total=self.http_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            result = await self._request_json(
                session,
                "POST",
                "/v1/api/user/search",
                json_data={"userInfo": account_name},
                token=login["token"],
            )
        resolved = self._pick_search_result(result, account_name)
        if not resolved:
            raise RuntimeError(f"未找到 Linyu 账号: {account_name}")
        return resolved

    @staticmethod
    def _pick_search_result(result: Any, account_name: str) -> Optional[Dict[str, str]]:
        data = result.get("data") if isinstance(result, dict) else None
        items: List[Dict[str, Any]] = []
        if isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            items = [data]
        if not items:
            return None

        target = str(account_name or "").strip()
        selected = None
        for item in items:
            candidate_account = str(item.get("account") or item.get("username") or item.get("name") or "").strip()
            if candidate_account == target:
                selected = item
                break
        if selected is None and len(items) == 1:
            selected = items[0]
        if selected is None:
            return None

        remote_user_id = str(selected.get("id") or selected.get("userId") or selected.get("user_id") or "").strip()
        resolved_account = str(selected.get("account") or account_name or "").strip()
        display_name = str(
            selected.get("nickname") or selected.get("name") or selected.get("displayName") or resolved_account
        ).strip()
        if not remote_user_id:
            return None
        return {
            "remote_user_id": remote_user_id,
            "account_name": resolved_account,
            "display_name": display_name or resolved_account,
        }


def _refresh_linyu_sessions() -> None:
    manager = get_linyu_session_manager()
    if manager:
        manager.request_refresh_all()


def _linyu_base_config() -> Dict[str, Any]:
    return dict((config.adapters_config or {}).get("linyu", {}) or {})


def _resolver() -> LinyuAccountResolver:
    return LinyuAccountResolver(_linyu_base_config())


def _candidate_linyu_credentials() -> List[tuple[str, str]]:
    candidates: List[tuple[str, str]] = []
    base = _linyu_base_config()
    if str(base.get("account") or "").strip() and str(base.get("password") or "").strip():
        candidates.append((str(base.get("account")).strip(), str(base.get("password")).strip()))
    for ai_account in account_registry.list_linyu_ai_accounts(enabled=True, include_bindings=False):
        account_name = str(ai_account.get("account_name") or ai_account.get("account") or "").strip()
        password = str(ai_account.get("password") or "").strip()
        if account_name and password and (account_name, password) not in candidates:
            candidates.append((account_name, password))
    return candidates


async def _resolve_linyu_user_account(account_name: str) -> Dict[str, str]:
    last_error = ""
    resolver = _resolver()
    for login_account, password in _candidate_linyu_credentials():
        try:
            return await resolver.resolve_user_by_account_name(account_name, login_account, password)
        except Exception as exc:
            last_error = str(exc)
    detail = "无法解析 Linyu 账号名，请先配置可登录的 Linyu AI 账号"
    if last_error:
        detail = f"无法解析 Linyu 账号名: {last_error}"
    raise HTTPException(status_code=400, detail=detail)


async def _normalize_account_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    platform = str(payload.get("platform") or "").strip()
    account_name = str(payload.get("account_name") or payload.get("remote_user_id") or "").strip()
    remote_user_id = str(payload.get("remote_user_id") or "").strip()
    display_name = str(payload.get("display_name") or "").strip()

    if not account_name and not remote_user_id:
        raise HTTPException(status_code=400, detail="请输入账号名")

    if platform == "linyu" and not remote_user_id:
        resolved = await _resolve_linyu_user_account(account_name)
        remote_user_id = resolved["remote_user_id"]
        account_name = resolved["account_name"] or account_name
        display_name = display_name or resolved.get("display_name") or account_name
    elif platform == "qq":
        remote_user_id = remote_user_id or account_name
        account_name = account_name or remote_user_id
        display_name = display_name or account_name
    elif platform == "linyu":
        account_name = account_name or remote_user_id
        display_name = display_name or account_name

    payload["account_name"] = account_name
    payload["remote_user_id"] = remote_user_id
    payload["display_name"] = display_name
    return payload


async def _normalize_platform_account_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    platform = str(payload.get("platform") or "").strip()
    account_name = str(payload.get("account_name") or "").strip()
    remote_user_id = str(payload.get("remote_user_id") or "").strip()

    if platform == "linyu" and account_name and not remote_user_id:
        resolved = await _resolve_linyu_user_account(account_name)
        payload["remote_user_id"] = resolved["remote_user_id"]
        payload["account_name"] = resolved["account_name"] or account_name
    elif platform == "qq":
        payload["remote_user_id"] = remote_user_id or account_name

    payload["enabled"] = bool(payload.get("enabled", True))
    payload["is_primary"] = bool(payload.get("is_primary", False))
    payload["metadata"] = payload.get("metadata") or {}
    return payload


async def _normalize_companion_payload(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    platform_accounts = payload.get("platform_accounts")
    if platform_accounts is None and existing is not None:
        platform_accounts = existing.get("platform_accounts") or []

    normalized_accounts: List[Dict[str, Any]] = []
    if platform_accounts is not None:
        for item in platform_accounts:
            normalized_accounts.append(await _normalize_platform_account_payload(dict(item)))

    payload["platform_accounts"] = normalized_accounts
    if "companion_name" in payload:
        payload["companion_name"] = str(payload.get("companion_name") or "").strip()
    elif existing is None and normalized_accounts:
        payload["companion_name"] = str(normalized_accounts[0].get("account_name") or "").strip()
    payload["metadata"] = payload.get("metadata") or {}
    return payload


def _normalize_ai_payload(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    account_name = str(payload.get("account_name") or payload.get("account") or "").strip()
    if not account_name and existing:
        account_name = str(existing.get("account_name") or existing.get("account") or "").strip()
    if account_name:
        payload["account_name"] = account_name
        payload["account"] = account_name
    if "companion_name" in payload:
        payload["companion_name"] = str(payload.get("companion_name") or "").strip() or account_name
    elif existing is None and account_name:
        payload["companion_name"] = account_name
    if "remote_user_id" in payload:
        payload["remote_user_id"] = str(payload.get("remote_user_id") or "").strip()
    return payload


async def _resolve_ai_remote_user_id(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    account_name = str(payload.get("account_name") or payload.get("account") or "").strip()
    password = str(payload.get("password") or "").strip()
    remote_user_id = str(payload.get("remote_user_id") or "").strip()
    if not account_name or remote_user_id:
        return payload
    if not password and existing:
        password = str(existing.get("password") or "").strip()
    if not password:
        return payload
    try:
        login = await _resolver().login(account_name, password)
        if login.get("remote_user_id"):
            payload["remote_user_id"] = login["remote_user_id"]
    except Exception:
        # 允许先保存账号，运行时仍会按登录结果获取 self_user_id。
        pass
    return payload


@router.get("/accounts")
async def list_accounts(
    platform: Optional[str] = Query(default=None, pattern="^(qq|linyu)$"),
    enabled: Optional[bool] = None,
):
    return {"accounts": account_registry.list_accounts(platform=platform, enabled=enabled)}


@router.post("/accounts/resolve/linyu")
async def resolve_linyu_account(request: ResolveAccountRequest):
    return await _resolve_linyu_user_account(request.account_name)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(request: AccountRequest):
    payload = await _normalize_account_payload(request.model_dump())
    return account_registry.upsert_account(**payload)


@router.put("/accounts/{account_id}")
async def update_account(account_id: int, request: AccountUpdateRequest):
    payload = request.model_dump(exclude_unset=True)
    if "platform" in payload and payload.get("platform") == "linyu":
        payload = await _normalize_account_payload(payload)
    account = account_registry.update_account(account_id, payload)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    _refresh_linyu_sessions()
    return account


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: int):
    if not account_registry.delete_account(account_id):
        raise HTTPException(status_code=404, detail="账号不存在")
    _refresh_linyu_sessions()
    return {"success": True}


@router.get("/ai-accounts/linyu")
async def list_linyu_ai_accounts(enabled: Optional[bool] = None):
    return {"accounts": account_registry.list_linyu_ai_accounts(enabled=enabled)}


@router.get("/companions")
async def list_companions(enabled: Optional[bool] = None):
    return {"companions": account_registry.list_companions(enabled=enabled)}


@router.post("/companions", status_code=status.HTTP_201_CREATED)
async def create_companion(request: CompanionRequest):
    payload = await _normalize_companion_payload(request.model_dump())
    if not payload.get("companion_name") and payload.get("platform_accounts"):
        payload["companion_name"] = str(payload["platform_accounts"][0].get("account_name") or "").strip()
    if not payload.get("companion_name"):
        raise HTTPException(status_code=400, detail="请输入伴侣名称")
    companion = account_registry.upsert_companion(**payload)
    _refresh_linyu_sessions()
    return companion


@router.put("/companions/{companion_id}")
async def update_companion(companion_id: int, request: CompanionUpdateRequest):
    existing = account_registry.get_companion(companion_id)
    if not existing:
        raise HTTPException(status_code=404, detail="伴侣不存在")
    payload = await _normalize_companion_payload(request.model_dump(exclude_unset=True), existing)
    companion = account_registry.update_companion(companion_id, payload)
    if not companion:
        raise HTTPException(status_code=404, detail="伴侣不存在")
    _refresh_linyu_sessions()
    return companion


@router.put("/companions/{companion_id}/bindings")
async def update_companion_bindings(companion_id: int, request: BindingRequest):
    companion = account_registry.set_companion_bindings(companion_id, request.user_account_ids)
    if not companion:
        raise HTTPException(status_code=404, detail="伴侣不存在")
    _refresh_linyu_sessions()
    return companion


@router.delete("/companions/{companion_id}")
async def delete_companion(companion_id: int):
    if not account_registry.delete_companion(companion_id):
        raise HTTPException(status_code=404, detail="伴侣不存在")
    _refresh_linyu_sessions()
    return {"success": True}


@router.post("/ai-accounts/linyu", status_code=status.HTTP_201_CREATED)
async def create_linyu_ai_account(request: CompanionRequest):
    payload = _normalize_ai_payload(request.model_dump())
    payload = await _resolve_ai_remote_user_id(payload)
    account = account_registry.upsert_linyu_ai_account(**payload)
    _refresh_linyu_sessions()
    return account


@router.put("/ai-accounts/linyu/{ai_account_id}")
async def update_linyu_ai_account(ai_account_id: int, request: CompanionUpdateRequest):
    existing = account_registry.get_linyu_ai_account(ai_account_id)
    if not existing:
        raise HTTPException(status_code=404, detail="AI 账号不存在")
    if request.platform_accounts is not None:
        linyu_accounts = [item.model_dump() for item in request.platform_accounts if item.platform == "linyu"]
        if not linyu_accounts:
            raise HTTPException(status_code=400, detail="至少保留一个 Linyu 平台账号")
        linyu = linyu_accounts[0]
        payload = {
            "companion_name": request.companion_name,
            "account_name": linyu.get("account_name"),
            "password": linyu.get("password"),
            "remote_user_id": linyu.get("remote_user_id"),
            "enabled": request.enabled if request.enabled is not None else linyu.get("enabled"),
            "bound_account_ids": request.bound_account_ids,
            "metadata": request.metadata,
        }
    else:
        payload = _normalize_ai_payload(request.model_dump(exclude_unset=True), existing)
    payload = await _resolve_ai_remote_user_id(payload, existing)
    account = account_registry.update_linyu_ai_account(ai_account_id, payload)
    if not account:
        raise HTTPException(status_code=404, detail="AI 账号不存在")
    _refresh_linyu_sessions()
    return account


@router.put("/ai-accounts/linyu/{ai_account_id}/bindings")
async def update_linyu_ai_bindings(ai_account_id: int, request: BindingRequest):
    account = account_registry.set_linyu_ai_bindings(ai_account_id, request.user_account_ids)
    if not account:
        raise HTTPException(status_code=404, detail="AI 账号不存在")
    _refresh_linyu_sessions()
    return account


@router.delete("/ai-accounts/linyu/{ai_account_id}")
async def delete_linyu_ai_account(ai_account_id: int):
    if not account_registry.delete_linyu_ai_account(ai_account_id):
        raise HTTPException(status_code=404, detail="AI 账号不存在")
    _refresh_linyu_sessions()
    return {"success": True}
