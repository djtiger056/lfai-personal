from __future__ import annotations

import asyncio
import copy
import json
import threading
from typing import Any, Dict, Optional

from ..config import config
from ..utils.config_merger import config_merger
from ..accounts import account_registry
from ..utils.companion_identity import companion_user_id, parse_companion_session_id
from .linyu import LinyuAdapter


_linyu_session_manager: Optional["LinyuSessionManager"] = None


def set_linyu_session_manager(manager: Optional["LinyuSessionManager"]) -> None:
    global _linyu_session_manager
    _linyu_session_manager = manager


def get_linyu_session_manager() -> Optional["LinyuSessionManager"]:
    return _linyu_session_manager


class LinyuSessionManager:
    """按用户维护独立的 Linyu 会话实例，并支持热重载。"""

    def __init__(self, bot):
        self.bot = bot
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        self._lock = threading.RLock()
        self.running = False

        self._adapters: Dict[str, LinyuAdapter] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._config_signatures: Dict[str, str] = {}

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._shutdown_event = asyncio.Event()
        self.running = True
        await self.refresh_all_sessions()
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        self.running = False
        if self._shutdown_event is not None:
            self._shutdown_event.set()
        owner_ids = list(self._adapters.keys())
        for owner_id in owner_ids:
            await self._stop_session(owner_id)

    def request_refresh_all(self) -> bool:
        if not self._loop or self._loop.is_closed():
            return False
        asyncio.run_coroutine_threadsafe(self.refresh_all_sessions(), self._loop)
        return True

    def request_refresh_user(self, owner_user_id: str) -> bool:
        if not self._loop or self._loop.is_closed():
            return False
        asyncio.run_coroutine_threadsafe(self.refresh_user_session(str(owner_user_id)), self._loop)
        return True

    def request_stop(self) -> bool:
        if not self._loop or self._loop.is_closed():
            return False
        asyncio.run_coroutine_threadsafe(self.stop(), self._loop)
        return True

    async def refresh_all_sessions(self) -> None:
        desired = await self._collect_user_linyu_configs()
        await self._sync_sessions(desired)

    async def refresh_user_session(self, owner_user_id: str) -> None:
        desired = await self._collect_user_linyu_configs(owner_user_id=str(owner_user_id))
        await self._sync_sessions(desired, owner_filter=str(owner_user_id))

    async def send_private(self, target: Dict[str, Any], payload: Any) -> bool:
        user = str(target.get("user_id") or "").strip()
        if not user:
            return False
        adapter = await self.get_adapter_for_target(target)
        if not adapter:
            return False

        if isinstance(payload, dict):
            text = payload.get("text")
            image = payload.get("image")
            if text:
                await adapter.send_private_message(user, text)
            if image:
                await adapter.send_image_message(user, image)
        else:
            await adapter.send_private_message(user, str(payload))
        return True

    async def send_raw_text(self, target: Dict[str, Any], text: str) -> bool:
        user = str(target.get("user_id") or "").strip()
        if not user or not text:
            return False
        adapter = await self.get_adapter_for_target(target)
        if not adapter:
            return False
        await adapter._send_text_once(user, text, is_group=False)
        return True

    async def get_adapter_for_target(self, target: Dict[str, Any]) -> Optional[LinyuAdapter]:
        target_user_id = str(target.get("user_id") or "").strip()
        session_id = str(target.get("session_id") or "").strip()
        companion_id = str(target.get("companion_id") or target.get("owner_user_id") or "").strip()

        with self._lock:
            adapter = self._adapters.get(companion_id) if companion_id else None
            if adapter:
                return adapter

            owner_from_session = self._owner_id_from_session_id(session_id)
            adapter = self._adapters.get(owner_from_session) if owner_from_session else None
            if adapter:
                return adapter

            adapter = self._adapters.get(target_user_id)
            if adapter:
                return adapter

            adapters = list(self._adapters.items())

        for owner_id, adapter in adapters:
            allowed_user_ids = set(str(item) for item in getattr(adapter, "allowed_user_ids", set()) or set())
            if target_user_id and target_user_id in allowed_user_ids:
                return adapter

            if session_id and session_id == owner_id:
                return adapter

        return None

    @staticmethod
    def _owner_id_from_session_id(session_id: str) -> str:
        parsed = parse_companion_session_id(session_id)
        if not parsed:
            return ""
        return companion_user_id(parsed["companion_id"])

    def get_status_snapshot(self) -> Dict[str, Dict[str, Any]]:
        snapshot: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            items = list(self._adapters.items())
        for owner_id, adapter in items:
            snapshot[owner_id] = adapter.get_runtime_status()
        return snapshot

    async def _sync_sessions(self, desired: Dict[str, Dict[str, Any]], owner_filter: Optional[str] = None) -> None:
        desired_ids = set(desired.keys())
        with self._lock:
            current_ids = set(self._adapters.keys())

        removable = current_ids - desired_ids
        if owner_filter is not None:
            removable = {item for item in removable if item == owner_filter}
        for owner_id in removable:
            await self._stop_session(owner_id)

        for owner_id, cfg in desired.items():
            signature = self._config_signature(cfg)
            with self._lock:
                existing_signature = self._config_signatures.get(owner_id)
            if existing_signature == signature and owner_id in current_ids:
                continue

            if owner_id in current_ids:
                await self._stop_session(owner_id)
            await self._start_session(owner_id, cfg, signature)

    async def _start_session(self, owner_id: str, linyu_cfg: Dict[str, Any], signature: str) -> None:
        adapter = LinyuAdapter(self.bot, linyu_cfg, owner_user_id=owner_id)
        task = asyncio.create_task(adapter.start(), name=f"linyu-session-{owner_id}")
        with self._lock:
            self._adapters[owner_id] = adapter
            self._tasks[owner_id] = task
            self._config_signatures[owner_id] = signature

    async def _stop_session(self, owner_id: str) -> None:
        with self._lock:
            adapter = self._adapters.pop(owner_id, None)
            task = self._tasks.pop(owner_id, None)
            self._config_signatures.pop(owner_id, None)

        if adapter:
            try:
                await adapter.stop()
            except Exception:
                pass

        if task:
            try:
                await asyncio.wait_for(task, timeout=5)
            except asyncio.TimeoutError:
                task.cancel()
            except Exception:
                pass

    async def _collect_user_linyu_configs(self, owner_user_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        collected: Dict[str, Dict[str, Any]] = {}
        global_linyu = copy.deepcopy((config.adapters_config or {}).get("linyu", {}) or {})

        ai_accounts = account_registry.list_linyu_ai_accounts(enabled=True)
        for ai_account in ai_accounts:
            owner_id = companion_user_id(ai_account["id"])
            if owner_user_id is not None and str(owner_user_id) != owner_id:
                continue

            user_linyu = {
                "enabled": bool(ai_account.get("enabled", True)),
                "account": ai_account.get("account_name") or ai_account.get("account", ""),
                "password": ai_account.get("password", ""),
            }
            metadata = ai_account.get("metadata") or {}
            if isinstance(metadata, dict):
                user_linyu.update(metadata.get("linyu", {}) if isinstance(metadata.get("linyu"), dict) else {})

            merged_linyu = config_merger.get_user_config(global_linyu, user_linyu, skip_empty=True)
            if not merged_linyu.get("enabled", False):
                continue

            for field in ("target_user_id", "target_user_account", "auto_bind_first_user"):
                merged_linyu.pop(field, None)

            # 用户级 Linyu 配置只负责提供个人 AI 账号，连接地址统一继承全局配置，
            # 聊天对象只使用账号管理里的显式绑定。
            for field in ("http_host", "http_port", "ws_host", "ws_port"):
                if field in global_linyu:
                    merged_linyu[field] = global_linyu.get(field)
                else:
                    merged_linyu.pop(field, None)

            bound_accounts = [
                account for account in (ai_account.get("bound_accounts") or [])
                if str(account.get("platform") or "") == "linyu"
                and bool(account.get("enabled", True))
                and str(account.get("remote_user_id") or "").strip()
            ]
            if not bound_accounts:
                continue

            merged_linyu["_companion_id"] = owner_id
            merged_linyu["_companion_name"] = str(ai_account.get("companion_name") or "").strip()
            merged_linyu["_ai_account_id"] = int(ai_account["id"])
            merged_linyu["_ai_account_name"] = str(ai_account.get("account_name") or ai_account.get("account") or "").strip()
            merged_linyu["_allowed_user_ids"] = [
                str(account.get("remote_user_id") or "").strip()
                for account in bound_accounts
            ]
            merged_linyu["_bound_accounts"] = [
                {
                    "id": account.get("id"),
                    "platform": account.get("platform"),
                    "account_name": account.get("account_name") or account.get("display_name") or account.get("remote_user_id"),
                    "remote_user_id": account.get("remote_user_id"),
                    "display_name": account.get("display_name") or account.get("account_name") or account.get("remote_user_id"),
                }
                for account in bound_accounts
            ]
            # Compatibility for old status consumers.
            merged_linyu["_target_user_id"] = merged_linyu["_allowed_user_ids"][0]
            merged_linyu["_target_display_name"] = str(
                merged_linyu["_bound_accounts"][0].get("display_name") or ""
            ).strip()

            if not merged_linyu.get("account") or not merged_linyu.get("password"):
                continue

            collected[owner_id] = merged_linyu

        return collected

    @staticmethod
    def _config_signature(linyu_cfg: Dict[str, Any]) -> str:
        return json.dumps(linyu_cfg, sort_keys=True, ensure_ascii=False)
