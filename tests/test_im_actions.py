from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.accounts import AccountRegistry
from backend.im_actions.manager import ActionContext, CompanionActionManager
from backend.im_actions.parser import extract_im_actions_block
from backend.utils.companion_identity import companion_user_id


class DummyBot:
    def __init__(self):
        self.generated_prompts: List[Dict[str, str]] = []
        self.generated_prompt_count_at_call: Dict[str, int] = {}
        self._last_generated_image = None

    def get_last_generated_image(self):
        return self._last_generated_image

    async def generate_image(self, prompt: str, user_id: str = "default", session_id: str | None = None):
        self.generated_prompts.append({
            "prompt": prompt,
            "user_id": user_id,
            "session_id": session_id or "",
        })
        return b"generated-image"


class DummyAdapter:
    def __init__(self, friend_list: List[Dict[str, Any]] | None = None):
        self.friend_list = friend_list or []
        self.requests: List[Dict[str, Any]] = []
        self.sent_images: List[Dict[str, Any]] = []
        self.ai_account_name = "bot-rain"
        self.token = "token-123"
        self.bot_ref = None

    async def _request_json(self, method: str, path: str, json_data: Dict[str, Any] | None = None):
        self.requests.append({"method": method, "path": path, "json": json_data})
        if path == "/v1/api/friend/list":
            return {"code": 0, "data": self.friend_list}
        if path == "/v1/api/user/info":
            return {"code": 0, "data": {"name": "原昵称", "portrait": "http://avatar", "signature": "old"}}
        if path == "/v1/api/red-packet/prepare":
            return {
                "code": 0,
                "msg": "红包意图已创建，待钱包系统接入",
                "data": {
                    "id": "rp-1",
                    "status": "pending_wallet_integration",
                    "wallet_status": "not_connected",
                },
            }
        if path == "/v1/api/talk/create":
            if self.bot_ref is not None:
                self.bot_ref.generated_prompt_count_at_call[path] = len(self.bot_ref.generated_prompts)
            return {"code": 0, "data": {"id": "talk-1", "text": (json_data or {}).get("text", "")}}
        if path in {
            "/v1/api/user/update",
            "/v1/api/message/send",
            "/v1/api/chat-group/create",
            "/v1/api/chat-group/invite",
            "/v1/api/chat-group/update/name",
            "/v1/api/friend/set/remark",
            "/v1/api/friend/set/group",
            "/v1/api/talk/delete",
        }:
            return {"code": 0, "data": json_data or {"ok": True}}
        raise AssertionError(f"unexpected request: {method} {path}")

    async def _request_raw(self, method: str, path: str, data: bytes, headers: Dict[str, str] | None = None):
        self.requests.append({"method": method, "path": path, "raw_size": len(data), "headers": headers or {}})
        return 200, '{"code":0,"data":{"url":"http://uploaded"}}'

    async def send_image_message(self, user_id: str, image_bytes: bytes):
        self.sent_images.append({"user_id": user_id, "size": len(image_bytes)})

    def _auth_headers(self):
        return {"x-token": self.token}


@pytest.fixture()
def registry_and_companion(tmp_path: Path):
    registry = AccountRegistry(tmp_path / "accounts.db")
    bound_account = registry.upsert_account(
        platform="linyu",
        account_name="alice",
        remote_user_id="u-alice",
        display_name="Alice",
        enabled=True,
    )
    companion = registry.upsert_linyu_ai_account(
        account_name="bot-rain",
        companion_name="小雨",
        password="pw",
        remote_user_id="bot-uuid",
        enabled=True,
        bound_account_ids=[bound_account["id"]],
    )
    return registry, companion, bound_account


@pytest.fixture()
def manager_env(tmp_path: Path, registry_and_companion):
    registry, companion, bound_account = registry_and_companion
    import backend.im_actions.manager as action_manager_module

    original_registry = action_manager_module.account_registry
    action_manager_module.account_registry = registry
    try:
        manager = CompanionActionManager(DummyBot())
        manager._db_path = tmp_path / "companion_actions.db"
        manager._ensure_tables()
        yield manager, registry, companion, bound_account
    finally:
        action_manager_module.account_registry = original_registry


def test_extract_im_actions_block_uses_last_valid_block():
    text = (
        "你好"
        "[IM_ACTIONS]{\"bad\": }[/IM_ACTIONS]"
        "中间"
        "[IM_ACTIONS]{\"actions\":[{\"name\":\"message.send_text\",\"params\":{\"text\":\"hi\"}}]}[/IM_ACTIONS]"
    )
    cleaned, payload = extract_im_actions_block(text)
    assert cleaned == "你好[IM_ACTIONS]{\"bad\": }[/IM_ACTIONS]中间"
    assert payload["actions"][0]["name"] == "message.send_text"


def test_companion_actions_config_crud(manager_env):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]

    cfg = manager.get_config(companion_id)
    assert cfg["enabled"] is False
    assert "message.send_text" in cfg["allow_actions"]

    updated = manager.update_config(
        companion_id,
        {
            "enabled": True,
            "allow_actions": ["profile.update", "message.send_text"],
            "rate_limits": {"max_actions_per_plan": 2},
        },
    )
    assert updated["enabled"] is True
    assert updated["allow_actions"] == ["profile.update", "message.send_text"]
    assert updated["rate_limits"]["max_actions_per_plan"] == 2
    assert updated["rate_limits"]["max_actions_per_hour"] == 10

    reloaded = manager.get_config(companion_id)
    assert reloaded["enabled"] is True
    assert reloaded["allow_actions"] == ["profile.update", "message.send_text"]


def test_update_config_preserves_existing_fields_on_partial_update(manager_env):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]

    manager.update_config(
        companion_id,
        {
            "enabled": True,
            "allow_actions": ["message.send_text", "message.send_image"],
            "rate_limits": {
                "max_actions_per_plan": 2,
                "max_actions_per_hour": 7,
                "max_actions_per_day": 11,
                "max_proactive_messages_per_friend_per_hour": 4,
            },
        },
    )
    updated = manager.update_config(
        companion_id,
        {
            "rate_limits": {
                "max_actions_per_plan": 5,
            },
        },
    )
    assert updated["enabled"] is True
    assert updated["allow_actions"] == ["message.send_text", "message.send_image"]
    assert updated["rate_limits"]["max_actions_per_plan"] == 5
    assert updated["rate_limits"]["max_actions_per_hour"] == 7
    assert updated["rate_limits"]["max_actions_per_day"] == 11
    assert updated["rate_limits"]["max_proactive_messages_per_friend_per_hour"] == 4


def _context_for(companion_id: str) -> ActionContext:
    return ActionContext(
        companion_user_id=companion_id,
        companion_pk=int(companion_id.split(":")[-1]),
        source="chat",
        trigger_message="test",
        session_id="session-1",
        raw_payload={},
    )


@pytest.mark.asyncio
async def test_execute_from_payload_blocks_actions_not_in_allowlist(manager_env):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]
    manager.update_config(companion_id, {"enabled": True, "allow_actions": ["profile.update"]})

    result = await manager.execute_from_payload(
        companion_user_id=companion_id,
        payload={"actions": [{"name": "message.send_text", "params": {"target": "Alice", "text": "hi"}}]},
        source="chat",
        trigger_message="send",
        session_id="session-1",
    )
    assert result["executed"] is True
    assert result["results"][0]["error"] == "action_not_allowed"

    logs = manager.list_logs(companion_id)
    assert logs[0]["status"] == "blocked"
    assert logs[0]["action_name"] == "message.send_text"


@pytest.mark.asyncio
async def test_execute_from_payload_applies_rate_limit_before_dispatch(manager_env, monkeypatch):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]
    manager.update_config(
        companion_id,
        {
            "enabled": True,
            "allow_actions": ["message.send_text"],
            "rate_limits": {"max_actions_per_hour": 1},
        },
    )

    called = {"count": 0}

    async def fake_dispatch(context, action_name, params):
        called["count"] += 1
        return {"ok": True}

    monkeypatch.setattr(manager, "_dispatch_action", fake_dispatch)

    first = await manager.execute_from_payload(
        companion_user_id=companion_id,
        payload={"actions": [{"name": "message.send_text", "params": {"target": "Alice", "text": "first"}}]},
        source="chat",
        trigger_message="first",
        session_id="session-1",
    )
    second = await manager.execute_from_payload(
        companion_user_id=companion_id,
        payload={"actions": [{"name": "message.send_text", "params": {"target": "Alice", "text": "second"}}]},
        source="chat",
        trigger_message="second",
        session_id="session-1",
    )

    assert first["results"][0]["ok"] is True
    assert second["results"][0]["error"] == "hourly_limit"
    assert called["count"] == 1


@pytest.mark.asyncio
async def test_proactive_friend_rate_limit_counts_text_and_image_actions(manager_env):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]
    cfg = manager.get_config(companion_id)
    rate_limits = dict(cfg["rate_limits"])
    rate_limits["max_proactive_messages_per_friend_per_hour"] = 1

    manager._log_action(
        companion_id=f"companion:{companion['id']}",
        source="proactive",
        session_id="session-1",
        action_name="message.send_image",
        target_key="friend-1",
        status="success",
        params={"target": "Alice"},
        result={"ok": True},
    )

    rate_error = manager._hit_rate_limit(
        f"companion:{companion['id']}",
        "friend-1",
        "proactive",
        "message.send_text",
        rate_limits,
    )
    assert rate_error == "friend_hourly_limit"


@pytest.mark.asyncio
async def test_resolve_target_prefers_bound_account(manager_env, monkeypatch):
    manager, _, companion, bound_account = manager_env
    companion_id = companion["companion_id"]

    async def fake_get_adapter(_):
        raise AssertionError("bound target should not require friend list lookup")

    monkeypatch.setattr(manager, "_get_adapter", fake_get_adapter)

    target = await manager._resolve_target(_context_for(companion_id), bound_account["display_name"])
    assert target == {
        "user_id": bound_account["remote_user_id"],
        "display_name": bound_account["display_name"],
        "source": "bound",
    }


@pytest.mark.asyncio
async def test_resolve_target_rejects_ambiguous_friend_matches(manager_env, monkeypatch):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]
    adapter = DummyAdapter(
        friend_list=[
            {"friendId": "f-1", "friendAccount": "alice1", "name": "同名好友", "remark": ""},
            {"friendId": "f-2", "friendAccount": "alice2", "name": "同名好友", "remark": ""},
        ]
    )
    async def fake_get_adapter(_companion_id):
        return adapter

    monkeypatch.setattr(manager, "_get_adapter", fake_get_adapter)

    with pytest.raises(RuntimeError, match="目标未命中或匹配歧义"):
        await manager._resolve_target(_context_for(companion_id), "同名好友")


@pytest.mark.asyncio
async def test_resolve_target_rejects_ambiguous_bound_matches(tmp_path: Path, monkeypatch):
    registry = AccountRegistry(tmp_path / "accounts.db")
    first = registry.upsert_account(
        platform="linyu",
        account_name="same-1",
        remote_user_id="u-1",
        display_name="同名",
        enabled=True,
    )
    second = registry.upsert_account(
        platform="linyu",
        account_name="same-2",
        remote_user_id="u-2",
        display_name="同名",
        enabled=True,
    )
    companion = registry.upsert_linyu_ai_account(
        account_name="bot-rain",
        companion_name="小雨",
        password="pw",
        remote_user_id="bot-uuid",
        enabled=True,
        bound_account_ids=[first["id"], second["id"]],
    )

    import backend.im_actions.manager as action_manager_module

    original_registry = action_manager_module.account_registry
    action_manager_module.account_registry = registry
    try:
        manager = CompanionActionManager(DummyBot())
        manager._db_path = tmp_path / "companion_actions.db"
        manager._ensure_tables()
        async def fake_get_adapter(_companion_id):
            return DummyAdapter()

        monkeypatch.setattr(manager, "_get_adapter", fake_get_adapter)
        with pytest.raises(RuntimeError, match="目标匹配歧义"):
            await manager._resolve_target(_context_for(companion["companion_id"]), "同名")
    finally:
        action_manager_module.account_registry = original_registry


@pytest.mark.asyncio
async def test_action_message_send_text_dispatches_to_linyu_send_api(manager_env, monkeypatch):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]
    adapter = DummyAdapter(friend_list=[{"friendId": "f-1", "friendAccount": "bob", "name": "小波", "remark": ""}])
    manager.update_config(companion_id, {"enabled": True, "allow_actions": ["message.send_text"]})
    async def fake_get_adapter(_companion_id):
        return adapter

    monkeypatch.setattr(manager, "_get_adapter", fake_get_adapter)

    result = await manager.execute_from_payload(
        companion_user_id=companion_id,
        payload={
            "actions": [
                {
                    "name": "message.send_text",
                    "params": {"target": "bob", "text": "你好呀"},
                }
            ]
        },
        source="chat",
        trigger_message="test",
        session_id="session-1",
    )

    send_request = next(item for item in adapter.requests if item["path"] == "/v1/api/message/send")
    assert send_request["json"]["toUserId"] == "f-1"
    assert send_request["json"]["msgContent"]["content"] == "你好呀"
    assert result["results"][0]["ok"] is True
    assert result["results"][0]["target"]["user_id"] == "f-1"


@pytest.mark.asyncio
async def test_action_moment_create_uploads_images_with_generated_content(manager_env, monkeypatch):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]
    adapter = DummyAdapter()
    adapter.bot_ref = manager.bot
    manager.update_config(companion_id, {"enabled": True, "allow_actions": ["moment.create"]})
    async def fake_get_adapter(_companion_id):
        return adapter

    monkeypatch.setattr(manager, "_get_adapter", fake_get_adapter)

    result = await manager.execute_from_payload(
        companion_user_id=companion_id,
        payload={
            "actions": [
                {
                    "name": "moment.create",
                    "params": {
                        "text": "今天心情很好",
                        "images": [{"prompt": "一个温柔头像风格的雨天自拍", "filename": "mood.png"}],
                    },
                }
            ]
        },
        source="proactive",
        trigger_message="tick",
        session_id="session-2",
    )

    assert result["results"][0]["ok"] is True
    assert result["results"][0]["talk_id"] == "talk-1"
    assert manager.bot.generated_prompts[0]["prompt"] == "一个温柔头像风格的雨天自拍"
    upload_request = next(item for item in adapter.requests if item["path"] == "/v1/api/talk/upload/img")
    assert upload_request["raw_size"] == len(b"generated-image")
    assert upload_request["headers"]["talkId"] == "talk-1"


@pytest.mark.asyncio
async def test_action_moment_create_generates_images_before_creating_talk(manager_env, monkeypatch):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]
    adapter = DummyAdapter()
    adapter.bot_ref = manager.bot
    manager.update_config(companion_id, {"enabled": True, "allow_actions": ["moment.create"]})

    async def fake_get_adapter(_companion_id):
        return adapter

    monkeypatch.setattr(manager, "_get_adapter", fake_get_adapter)

    await manager.execute_from_payload(
        companion_user_id=companion_id,
        payload={
            "actions": [
                {
                    "name": "moment.create",
                    "params": {
                        "text": "先有图再发动态",
                        "images": [{"prompt": "宿舍窗外夜景", "filename": "night.png"}],
                    },
                }
            ]
        },
        source="chat",
        trigger_message="发个朋友圈",
        session_id="session-3",
    )

    assert manager.bot.generated_prompts[0]["prompt"] == "宿舍窗外夜景"
    assert adapter.bot_ref.generated_prompt_count_at_call["/v1/api/talk/create"] == 1


@pytest.mark.asyncio
async def test_action_avatar_update_reuses_last_generated_image(manager_env, monkeypatch):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]
    adapter = DummyAdapter()
    manager.update_config(companion_id, {"enabled": True, "allow_actions": ["avatar.update"]})
    manager.bot._last_generated_image = {"image_data": b"avatar-bytes"}
    async def fake_get_adapter(_companion_id):
        return adapter

    monkeypatch.setattr(manager, "_get_adapter", fake_get_adapter)

    result = await manager.execute_from_payload(
        companion_user_id=companion_id,
        payload={
            "actions": [
                {
                    "name": "avatar.update",
                    "params": {"use_last_generated": True, "filename": "avatar.png"},
                }
            ]
        },
        source="chat",
        trigger_message="test",
        session_id="session-3",
    )

    assert result["results"][0]["ok"] is True
    upload_request = next(item for item in adapter.requests if item["path"] == "/v1/api/user/upload/portrait")
    assert upload_request["raw_size"] == len(b"avatar-bytes")
    assert upload_request["headers"]["name"] == "avatar.png"


@pytest.mark.asyncio
async def test_action_group_create_resolves_targets_and_calls_group_api(manager_env, monkeypatch):
    manager, _, companion, _ = manager_env
    companion_id = companion["companion_id"]
    adapter = DummyAdapter(
        friend_list=[
            {"friendId": "f-1", "friendAccount": "bob", "name": "小波", "remark": ""},
            {"friendId": "f-2", "friendAccount": "carol", "name": "小卡", "remark": ""},
        ]
    )
    manager.update_config(companion_id, {"enabled": True, "allow_actions": ["group.create"]})
    async def fake_get_adapter(_companion_id):
        return adapter

    monkeypatch.setattr(manager, "_get_adapter", fake_get_adapter)

    result = await manager.execute_from_payload(
        companion_user_id=companion_id,
        payload={
            "actions": [
                {
                    "name": "group.create",
                    "params": {"name": "新群聊", "targets": ["bob", "carol"]},
                }
            ]
        },
        source="chat",
        trigger_message="拉群",
        session_id="session-4",
    )

    request = next(item for item in adapter.requests if item["path"] == "/v1/api/chat-group/create")
    assert request["json"]["users"] == [
        {"userId": "f-1", "name": "小波"},
        {"userId": "f-2", "name": "小卡"},
    ]
    assert result["results"][0]["ok"] is True


@pytest.mark.asyncio
async def test_action_red_packet_prepare_returns_pending_wallet_status(manager_env, monkeypatch):
    manager, _, companion, bound_account = manager_env
    companion_id = companion["companion_id"]
    adapter = DummyAdapter()
    manager.update_config(companion_id, {"enabled": True, "allow_actions": ["red_packet.prepare"]})
    async def fake_get_adapter(_companion_id):
        return adapter

    monkeypatch.setattr(manager, "_get_adapter", fake_get_adapter)

    result = await manager.execute_from_payload(
        companion_user_id=companion_id,
        payload={
            "actions": [
                {
                    "name": "red_packet.prepare",
                    "params": {
                        "target": bound_account["display_name"],
                        "amount": "66.00",
                        "greeting": "恭喜发财",
                    },
                }
            ]
        },
        source="proactive",
        trigger_message="tick",
        session_id="session-5",
    )

    action_result = result["results"][0]
    assert action_result["ok"] is True
    assert action_result["data"]["status"] == "pending_wallet_integration"
    assert action_result["data"]["wallet_status"] == "not_connected"


def test_list_logs_returns_params_and_result_payloads(manager_env):
    manager, _, companion, _ = manager_env
    companion_id = companion_user_id(companion["id"])
    manager._log_action(
        companion_id=companion_id,
        source="chat",
        session_id="session-1",
        action_name="message.send_text",
        target_key="Alice",
        status="success",
        params={"text": "hello"},
        result={"ok": True, "message_id": "m-1"},
    )

    logs = manager.list_logs(companion_id)
    assert logs[0]["params"]["text"] == "hello"
    assert logs[0]["result"]["message_id"] == "m-1"
