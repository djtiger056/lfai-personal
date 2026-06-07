from __future__ import annotations

import base64
import copy
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

import aiohttp

from backend.accounts import account_registry
from backend.config import config
from backend.utils.companion_identity import parse_companion_user_id
from backend.utils.datetime_utils import from_isoformat, get_now


DEFAULT_ALLOWED_ACTIONS = [
    "profile.update",
    "avatar.update",
    "moment.create",
    "moment.delete",
    "message.send_text",
    "message.send_image",
    "group.create",
    "group.invite",
    "group.rename",
    "friend.set_remark",
    "friend.set_group",
    "red_packet.prepare",
]

DEFAULT_RATE_LIMITS = {
    "max_actions_per_plan": 3,
    "max_actions_per_hour": 10,
    "max_actions_per_day": 50,
    "max_proactive_messages_per_friend_per_hour": 10,
}

DEFAULT_CONFIG = {
    "enabled": False,
    "autonomy_mode": "auto",
    "target_scope": "bound_and_friends",
    "allow_actions": DEFAULT_ALLOWED_ACTIONS,
    "rate_limits": DEFAULT_RATE_LIMITS,
}

CATALOG: List[Dict[str, Any]] = [
    {"name": "profile.update", "risk": "low", "description": "修改昵称、签名、生日、性别等资料"},
    {"name": "avatar.update", "risk": "low", "description": "更新当前伴侣账号头像"},
    {"name": "moment.create", "risk": "low", "description": "发布朋友圈/说说，支持配图"},
    {"name": "moment.delete", "risk": "medium", "description": "删除自己发出的朋友圈/说说"},
    {"name": "message.send_text", "risk": "medium", "description": "向绑定对象或已有好友发送文本"},
    {"name": "message.send_image", "risk": "medium", "description": "向绑定对象或已有好友发送图片"},
    {"name": "group.create", "risk": "medium", "description": "创建群聊"},
    {"name": "group.invite", "risk": "medium", "description": "邀请成员进群"},
    {"name": "group.rename", "risk": "medium", "description": "修改群名称"},
    {"name": "friend.set_remark", "risk": "low", "description": "设置好友备注"},
    {"name": "friend.set_group", "risk": "low", "description": "设置好友分组"},
    {"name": "red_packet.prepare", "risk": "medium", "description": "创建红包意图占位，等待钱包系统接入"},
]


@dataclass
class ActionContext:
    companion_user_id: str
    companion_pk: int
    source: str
    trigger_message: str
    session_id: str
    raw_payload: Dict[str, Any]


class CompanionActionManager:
    def __init__(self, bot):
        self.bot = bot
        self._db_path = Path("data") / "companion_actions.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS action_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    companion_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    target_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    error_message TEXT NOT NULL DEFAULT '',
                    params_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )

    def get_catalog(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(CATALOG)

    def get_config(self, companion_user_id: str) -> Dict[str, Any]:
        companion_pk = self._resolve_companion_pk(companion_user_id)
        companion = account_registry.get_companion(companion_pk)
        metadata = (companion or {}).get("metadata") or {}
        action_cfg = metadata.get("linyu_actions") if isinstance(metadata, dict) else None
        return self._merge_config(action_cfg if isinstance(action_cfg, dict) else {})

    def update_config(self, companion_user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        companion_pk = self._resolve_companion_pk(companion_user_id)
        companion = account_registry.get_companion(companion_pk)
        if not companion:
            raise ValueError("未找到伴侣账号")
        metadata = companion.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        current_cfg = metadata.get("linyu_actions") if isinstance(metadata.get("linyu_actions"), dict) else {}
        merged_input = copy.deepcopy(current_cfg) if isinstance(current_cfg, dict) else {}
        incoming = updates if isinstance(updates, dict) else {}
        for key, value in incoming.items():
            if key == "rate_limits" and isinstance(value, dict):
                base_rate_limits = merged_input.get("rate_limits") if isinstance(merged_input.get("rate_limits"), dict) else {}
                merged_input["rate_limits"] = {**base_rate_limits, **value}
            else:
                merged_input[key] = value
        merged = self._merge_config(merged_input)
        metadata["linyu_actions"] = merged
        updated = account_registry.update_companion(companion_pk, {"metadata": metadata})
        if not updated:
            raise ValueError("保存伴侣动作配置失败")
        return merged

    def list_logs(self, companion_user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        companion_pk = self._resolve_companion_pk(companion_user_id)
        resolved = f"companion:{companion_pk}"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM action_logs
                WHERE companion_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (resolved, max(1, min(limit, 500))),
            ).fetchall()
        return [self._row_to_log(row) for row in rows]

    async def execute_from_payload(
        self,
        *,
        companion_user_id: str,
        payload: Dict[str, Any],
        source: str,
        trigger_message: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        companion_pk = self._resolve_companion_pk(companion_user_id)
        cfg = self.get_config(companion_user_id)
        context = ActionContext(
            companion_user_id=companion_user_id,
            companion_pk=companion_pk,
            source=source,
            trigger_message=str(trigger_message or ""),
            session_id=str(session_id or companion_user_id),
            raw_payload=payload or {},
        )

        if not cfg.get("enabled", False):
            return {"executed": False, "reason": "disabled", "results": []}

        actions = payload.get("actions")
        if not isinstance(actions, list) or not actions:
            return {"executed": False, "reason": "empty_actions", "results": []}

        max_actions = int((cfg.get("rate_limits") or {}).get("max_actions_per_plan", 3) or 3)
        actions = actions[: max(1, max_actions)]

        results: List[Dict[str, Any]] = []
        for action in actions:
            result = await self._execute_single_action(context, cfg, action)
            results.append(result)

        return {"executed": True, "results": results}

    def _resolve_companion_pk(self, companion_user_id: str) -> int:
        companion_pk = parse_companion_user_id(str(companion_user_id or "").strip())
        if companion_pk is None:
            raise ValueError("伴侣身份格式无效")
        return companion_pk

    def _merge_config(self, action_cfg: Dict[str, Any]) -> Dict[str, Any]:
        merged = copy.deepcopy(DEFAULT_CONFIG)
        if isinstance(action_cfg, dict):
            merged.update({
                "enabled": bool(action_cfg.get("enabled", merged["enabled"])),
                "autonomy_mode": str(action_cfg.get("autonomy_mode") or merged["autonomy_mode"]),
                "target_scope": str(action_cfg.get("target_scope") or merged["target_scope"]),
            })
            allow_actions = action_cfg.get("allow_actions")
            if isinstance(allow_actions, list):
                merged["allow_actions"] = [str(item).strip() for item in allow_actions if str(item).strip()]
            rate_limits = action_cfg.get("rate_limits")
            if isinstance(rate_limits, dict):
                merged["rate_limits"].update({
                    key: int(rate_limits.get(key, merged["rate_limits"][key]) or merged["rate_limits"][key])
                    for key in DEFAULT_RATE_LIMITS
                })
        return merged

    def _row_to_log(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["params"] = self._json_loads(data.pop("params_json", "{}"))
        data["result"] = self._json_loads(data.pop("result_json", "{}"))
        return data

    @staticmethod
    def _json_loads(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value or ""))
        except Exception:
            return {}

    def _log_action(
        self,
        *,
        companion_id: str,
        source: str,
        session_id: str,
        action_name: str,
        target_key: str,
        status: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        error_message: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO action_logs(
                    companion_id, source, session_id, action_name, target_key,
                    status, error_message, params_json, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    companion_id,
                    source,
                    session_id,
                    action_name,
                    target_key,
                    status,
                    error_message,
                    json.dumps(params or {}, ensure_ascii=False),
                    json.dumps(result or {}, ensure_ascii=False),
                    get_now().isoformat(),
                ),
            )

    @staticmethod
    def _is_proactive_private_message_action(action_name: str) -> bool:
        return action_name in {"message.send_text", "message.send_image"}

    def _hit_rate_limit(self, companion_id: str, target_key: str, source: str, action_name: str, rate_limits: Dict[str, int]) -> Optional[str]:
        now = get_now()
        one_hour_ago = now.timestamp() - 3600
        one_day_ago = now.timestamp() - 86400
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT action_name, target_key, source, created_at FROM action_logs WHERE companion_id = ?",
                (companion_id,),
            ).fetchall()
        hourly = 0
        daily = 0
        friend_hourly = 0
        for row in rows:
            created_at = row["created_at"]
            try:
                ts = from_isoformat(created_at).timestamp()
            except Exception:
                continue
            if ts >= one_hour_ago:
                hourly += 1
            if ts >= one_day_ago:
                daily += 1
            if (
                self._is_proactive_private_message_action(action_name)
                and self._is_proactive_private_message_action(str(row["action_name"] or ""))
                and row["target_key"] == target_key
                and row["source"] == "proactive"
                and source == "proactive"
                and ts >= one_hour_ago
            ):
                friend_hourly += 1

        if hourly >= int(rate_limits.get("max_actions_per_hour", 10) or 10):
            return "hourly_limit"
        if daily >= int(rate_limits.get("max_actions_per_day", 50) or 50):
            return "daily_limit"
        if (
            self._is_proactive_private_message_action(action_name)
            and source == "proactive"
            and friend_hourly >= int(rate_limits.get("max_proactive_messages_per_friend_per_hour", 10) or 10)
        ):
            return "friend_hourly_limit"
        return None

    async def _execute_single_action(
        self,
        context: ActionContext,
        cfg: Dict[str, Any],
        action_payload: Any,
    ) -> Dict[str, Any]:
        if not isinstance(action_payload, dict):
            return {"ok": False, "error": "invalid_action_payload"}

        action_name = str(action_payload.get("name") or "").strip()
        params = action_payload.get("params") if isinstance(action_payload.get("params"), dict) else {}
        companion_id = f"companion:{context.companion_pk}"
        target_key = str(params.get("target") or params.get("target_id") or "")

        if action_name not in cfg.get("allow_actions", []):
            result = {"ok": False, "error": "action_not_allowed"}
            self._log_action(
                companion_id=companion_id,
                source=context.source,
                session_id=context.session_id,
                action_name=action_name or "unknown",
                target_key=target_key,
                status="blocked",
                params=params,
                result=result,
                error_message="action_not_allowed",
            )
            return result

        rate_error = self._hit_rate_limit(companion_id, target_key, context.source, action_name, cfg.get("rate_limits") or {})
        if rate_error:
            result = {"ok": False, "error": rate_error}
            self._log_action(
                companion_id=companion_id,
                source=context.source,
                session_id=context.session_id,
                action_name=action_name,
                target_key=target_key,
                status="blocked",
                params=params,
                result=result,
                error_message=rate_error,
            )
            return result

        try:
            result = await self._dispatch_action(context, action_name, params)
            self._log_action(
                companion_id=companion_id,
                source=context.source,
                session_id=context.session_id,
                action_name=action_name,
                target_key=target_key,
                status="success" if result.get("ok") else "failed",
                params=params,
                result=result,
                error_message=str(result.get("error") or ""),
            )
            return result
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
            self._log_action(
                companion_id=companion_id,
                source=context.source,
                session_id=context.session_id,
                action_name=action_name,
                target_key=target_key,
                status="failed",
                params=params,
                result=result,
                error_message=str(exc),
            )
            return result

    async def _dispatch_action(self, context: ActionContext, action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "profile.update":
            return await self._action_profile_update(context, params)
        if action_name == "avatar.update":
            return await self._action_avatar_update(context, params)
        if action_name == "moment.create":
            return await self._action_moment_create(context, params)
        if action_name == "moment.delete":
            return await self._action_moment_delete(context, params)
        if action_name == "message.send_text":
            return await self._action_message_send_text(context, params)
        if action_name == "message.send_image":
            return await self._action_message_send_image(context, params)
        if action_name == "group.create":
            return await self._action_group_create(context, params)
        if action_name == "group.invite":
            return await self._action_group_invite(context, params)
        if action_name == "group.rename":
            return await self._action_group_rename(context, params)
        if action_name == "friend.set_remark":
            return await self._action_friend_set_remark(context, params)
        if action_name == "friend.set_group":
            return await self._action_friend_set_group(context, params)
        if action_name == "red_packet.prepare":
            return await self._action_red_packet_prepare(context, params)
        return {"ok": False, "error": f"unsupported_action:{action_name}"}

    async def _get_adapter(self, companion_user_id: str):
        from backend.adapters.linyu_manager import get_linyu_session_manager

        manager = get_linyu_session_manager()
        if not manager:
            raise RuntimeError("LinyuSessionManager 未启动")
        adapter = await manager.get_adapter_for_target(
            {"companion_id": companion_user_id, "owner_user_id": companion_user_id, "user_id": companion_user_id}
        )
        if not adapter:
            raise RuntimeError("未找到对应伴侣的 Linyu 会话")
        return adapter

    async def _request_json(self, adapter, method: str, path: str, json_data: Optional[Dict[str, Any]] = None):
        result = await adapter._request_json(method, path, json_data=json_data)
        if isinstance(result, dict) and result.get("code") not in (None, 0, 200):
            raise RuntimeError(str(result.get("msg") or result.get("message") or result))
        return result

    async def _request_upload(self, adapter, method: str, path: str, data: bytes, headers: Dict[str, str]) -> Any:
        status, text = await adapter._request_raw(method, path, data=data, headers=headers)
        if status != 200:
            raise RuntimeError(f"HTTP {status}: {text[:160]}")
        try:
            return json.loads(text)
        except Exception:
            return text

    def _find_bound_target(self, companion: Dict[str, Any], token: str) -> Optional[Dict[str, Any]]:
        token = str(token or "").strip()
        if not token:
            return None
        matches = []
        for account in companion.get("bound_accounts") or []:
            if str(account.get("platform") or "") != "linyu":
                continue
            candidates = {
                str(account.get("remote_user_id") or "").strip(),
                str(account.get("account_name") or "").strip(),
                str(account.get("display_name") or "").strip(),
            }
            if token in candidates:
                matches.append(account)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError("目标匹配歧义")
        return None

    async def _resolve_target(self, context: ActionContext, target_token: str) -> Dict[str, Any]:
        companion = account_registry.get_companion(context.companion_pk)
        if not companion:
            raise RuntimeError("未找到伴侣账号")
        bound = self._find_bound_target(companion, target_token)
        if bound:
            return {
                "user_id": str(bound.get("remote_user_id") or ""),
                "display_name": str(bound.get("display_name") or bound.get("account_name") or target_token),
                "source": "bound",
            }

        adapter = await self._get_adapter(context.companion_user_id)
        friend_list = await self._request_json(adapter, "GET", "/v1/api/friend/list")
        data = friend_list.get("data") if isinstance(friend_list, dict) else None
        items = data if isinstance(data, list) else []
        matches = []
        for item in items:
            if not isinstance(item, dict):
                continue
            candidates = {
                str(item.get("friendId") or item.get("id") or "").strip(),
                str(item.get("friendAccount") or item.get("account") or "").strip(),
                str(item.get("name") or "").strip(),
                str(item.get("remark") or "").strip(),
            }
            if target_token in candidates:
                matches.append(item)
        if len(matches) != 1:
            raise RuntimeError("目标未命中或匹配歧义")
        item = matches[0]
        return {
            "user_id": str(item.get("friendId") or item.get("id") or "").strip(),
            "display_name": str(item.get("remark") or item.get("name") or target_token),
            "source": "friend",
        }

    async def _resolve_image_bytes(self, context: ActionContext, params: Dict[str, Any]) -> bytes:
        image_url = str(params.get("image_url") or "").strip()
        if image_url:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"图片下载失败: HTTP {resp.status}")
                    return await resp.read()

        reuse_last = bool(params.get("use_last_generated", False))
        if reuse_last:
            if hasattr(self.bot, "peek_last_generated_image"):
                last_image = self.bot.peek_last_generated_image()
            else:
                last_image = self.bot.get_last_generated_image()
            if last_image and last_image.get("image_data"):
                return last_image["image_data"]

        prompt = str(params.get("prompt") or "").strip()
        if prompt:
            image_data = await self.bot.generate_image(prompt, user_id=context.companion_user_id, session_id=context.session_id)
            if image_data:
                return image_data

        raise RuntimeError("缺少可用图片素材")

    async def _action_profile_update(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        info_result = await self._request_json(adapter, "GET", "/v1/api/user/info")
        current = info_result.get("data") if isinstance(info_result, dict) else {}
        current = current if isinstance(current, dict) else {}
        payload = {
            "name": str(params.get("name") or current.get("name") or current.get("nickname") or adapter.ai_account_name or "").strip() or "AI伴侣",
            "sex": params.get("sex") if params.get("sex") is not None else current.get("sex"),
            "birthday": params.get("birthday") if params.get("birthday") is not None else current.get("birthday"),
            "signature": params.get("signature") if params.get("signature") is not None else current.get("signature"),
            "portrait": str(current.get("portrait") or ""),
        }
        result = await self._request_json(adapter, "POST", "/v1/api/user/update", json_data=payload)
        return {"ok": True, "data": result.get("data") if isinstance(result, dict) else result}

    async def _action_avatar_update(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        image_bytes = await self._resolve_image_bytes(context, params)
        filename = str(params.get("filename") or "avatar.png")
        content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        headers = adapter._auth_headers()
        headers.update({
            "name": filename,
            "type": content_type,
            "size": str(len(image_bytes)),
        })
        result = await self._request_upload(adapter, "POST", "/v1/api/user/upload/portrait", image_bytes, headers)
        return {"ok": True, "data": result.get("data") if isinstance(result, dict) else result}

    async def _action_moment_create(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        resolved_images: List[Tuple[bytes, str]] = []
        image_specs = params.get("images")
        if isinstance(image_specs, list):
            for index, spec in enumerate(image_specs):
                image_params = spec if isinstance(spec, dict) else {"image_url": str(spec or "")}
                image_bytes = await self._resolve_image_bytes(context, image_params)
                filename = str(image_params.get("filename") or f"moment-{index + 1}.png")
                resolved_images.append((image_bytes, filename))

        create_payload = {
            "text": str(params.get("text") or "").strip(),
            "permission": params.get("permission") if isinstance(params.get("permission"), list) else [],
        }
        result = await self._request_json(adapter, "POST", "/v1/api/talk/create", json_data=create_payload)
        talk = result.get("data") if isinstance(result, dict) else {}
        talk_id = str((talk or {}).get("id") or "")
        if not talk_id:
            raise RuntimeError("创建朋友圈失败：缺少 talkId")

        if resolved_images:
            for image_bytes, filename in resolved_images:
                headers = adapter._auth_headers()
                headers.update({
                    "talkId": talk_id,
                    "name": filename,
                    "type": "image/png" if filename.lower().endswith(".png") else "image/jpeg",
                    "size": str(len(image_bytes)),
                })
                await self._request_upload(adapter, "POST", "/v1/api/talk/upload/img", image_bytes, headers)

        return {"ok": True, "talk_id": talk_id, "data": talk}

    async def _action_moment_delete(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        talk_id = str(params.get("talk_id") or "").strip()
        if not talk_id:
            raise RuntimeError("缺少 talk_id")
        result = await self._request_json(adapter, "POST", "/v1/api/talk/delete", json_data={"talkId": talk_id})
        return {"ok": True, "data": result.get("data") if isinstance(result, dict) else result}

    async def _action_message_send_text(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        target = await self._resolve_target(context, str(params.get("target") or ""))
        payload = {
            "toUserId": target["user_id"],
            "source": "user",
            "msgContent": {
                "type": "text",
                "content": str(params.get("text") or "").strip(),
            },
        }
        result = await self._request_json(adapter, "POST", "/v1/api/message/send", json_data=payload)
        return {"ok": True, "target": target, "data": result.get("data") if isinstance(result, dict) else result}

    async def _action_message_send_image(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        target = await self._resolve_target(context, str(params.get("target") or ""))
        image_bytes = await self._resolve_image_bytes(context, params)
        await adapter.send_image_message(target["user_id"], image_bytes)
        return {"ok": True, "target": target, "bytes": len(image_bytes)}

    async def _action_group_create(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        users = []
        for raw_target in params.get("targets") or []:
            target = await self._resolve_target(context, str(raw_target))
            users.append({"userId": target["user_id"], "name": target["display_name"]})
        payload = {
            "name": str(params.get("name") or "").strip() or "新群聊",
            "notice": str(params.get("notice") or "").strip(),
            "users": users,
        }
        result = await self._request_json(adapter, "POST", "/v1/api/chat-group/create", json_data=payload)
        return {"ok": True, "data": result.get("data") if isinstance(result, dict) else result}

    async def _action_group_invite(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        group_id = str(params.get("group_id") or "").strip()
        if not group_id:
            raise RuntimeError("缺少 group_id")
        user_ids = []
        for raw_target in params.get("targets") or []:
            target = await self._resolve_target(context, str(raw_target))
            user_ids.append(target["user_id"])
        result = await self._request_json(adapter, "POST", "/v1/api/chat-group/invite", json_data={"groupId": group_id, "userIds": user_ids})
        return {"ok": True, "data": result.get("data") if isinstance(result, dict) else result}

    async def _action_group_rename(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        payload = {
            "groupId": str(params.get("group_id") or "").strip(),
            "name": str(params.get("name") or "").strip(),
        }
        if not payload["groupId"] or not payload["name"]:
            raise RuntimeError("缺少 group_id 或 name")
        result = await self._request_json(adapter, "POST", "/v1/api/chat-group/update/name", json_data=payload)
        return {"ok": True, "data": result.get("data") if isinstance(result, dict) else result}

    async def _action_friend_set_remark(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        target = await self._resolve_target(context, str(params.get("target") or ""))
        payload = {"friendId": target["user_id"], "remark": str(params.get("remark") or "").strip()}
        result = await self._request_json(adapter, "POST", "/v1/api/friend/set/remark", json_data=payload)
        return {"ok": True, "target": target, "data": result.get("data") if isinstance(result, dict) else result}

    async def _action_friend_set_group(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        target = await self._resolve_target(context, str(params.get("target") or ""))
        payload = {"friendId": target["user_id"], "groupId": str(params.get("group_id") or params.get("group_name") or "").strip()}
        result = await self._request_json(adapter, "POST", "/v1/api/friend/set/group", json_data=payload)
        return {"ok": True, "target": target, "data": result.get("data") if isinstance(result, dict) else result}

    async def _action_red_packet_prepare(self, context: ActionContext, params: Dict[str, Any]) -> Dict[str, Any]:
        adapter = await self._get_adapter(context.companion_user_id)
        target = None
        target_name = ""
        target_user_id = ""
        if params.get("target"):
            target = await self._resolve_target(context, str(params.get("target") or ""))
            target_name = target.get("display_name") or ""
            target_user_id = target.get("user_id") or ""
        payload = {
            "targetUserId": target_user_id,
            "targetDisplayName": target_name,
            "amount": params.get("amount"),
            "greeting": str(params.get("greeting") or "").strip(),
            "note": str(params.get("note") or "").strip(),
        }
        result = await self._request_json(adapter, "POST", "/v1/api/red-packet/prepare", json_data=payload)
        return {"ok": True, "target": target, "data": result.get("data") if isinstance(result, dict) else result}
