import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.linyu_manager import LinyuSessionManager


def _base_linyu_config(enabled: bool = True):
    return {
        "adapters": {
            "linyu": {
                "enabled": enabled,
                "http_host": "10.0.0.8",
                "http_port": 9200,
                "ws_host": "10.0.0.8",
                "ws_port": 9100,
                "target_user_id": "old-target",
                "target_user_account": "old-account",
                "auto_bind_first_user": True,
            }
        }
    }


@pytest.mark.asyncio
async def test_collect_linyu_configs_uses_companion_accounts_and_bindings(monkeypatch):
    manager = LinyuSessionManager(bot=object())

    monkeypatch.setattr(
        "backend.adapters.linyu_manager.config._config",
        _base_linyu_config(enabled=False),
        raising=False,
    )
    monkeypatch.setattr(
        "backend.adapters.linyu_manager.account_registry.list_linyu_ai_accounts",
        lambda enabled=None: [
            {
                "id": 1,
                "companion_name": "小雨",
                "account_name": "ai_1",
                "account": "ai_1",
                "password": "pwd1",
                "enabled": True,
                "metadata": {},
                "bound_accounts": [
                    {
                        "id": 10,
                        "platform": "linyu",
                        "account_name": "alice",
                        "remote_user_id": "uuid-1",
                        "display_name": "Alice",
                        "enabled": True,
                    },
                    {
                        "id": 11,
                        "platform": "linyu",
                        "account_name": "bob",
                        "remote_user_id": "uuid-2",
                        "display_name": "Bob",
                        "enabled": True,
                    },
                ],
            },
            {
                "id": 2,
                "companion_name": "空伴侣",
                "account_name": "ai_2",
                "account": "ai_2",
                "password": "pwd2",
                "enabled": True,
                "metadata": {},
                "bound_accounts": [],
            },
        ],
    )

    configs = await manager._collect_user_linyu_configs()

    assert set(configs.keys()) == {"companion:1"}
    cfg = configs["companion:1"]
    assert cfg["account"] == "ai_1"
    assert cfg["_companion_id"] == "companion:1"
    assert cfg["_companion_name"] == "小雨"
    assert cfg["_ai_account_id"] == 1
    assert cfg["_ai_account_name"] == "ai_1"
    assert cfg["_allowed_user_ids"] == ["uuid-1", "uuid-2"]
    assert [item["account_name"] for item in cfg["_bound_accounts"]] == ["alice", "bob"]
    assert cfg["_target_user_id"] == "uuid-1"
    assert cfg["_target_display_name"] == "Alice"
    assert "target_user_id" not in cfg
    assert "target_user_account" not in cfg
    assert "auto_bind_first_user" not in cfg


@pytest.mark.asyncio
async def test_collect_linyu_configs_does_not_start_global_or_unbound_sessions(monkeypatch):
    manager = LinyuSessionManager(bot=object())

    monkeypatch.setattr(
        "backend.adapters.linyu_manager.config._config",
        _base_linyu_config(enabled=True),
        raising=False,
    )
    monkeypatch.setattr(
        "backend.adapters.linyu_manager.account_registry.list_linyu_ai_accounts",
        lambda enabled=None: [
            {
                "id": 3,
                "companion_name": "未绑定",
                "account_name": "ai_3",
                "account": "ai_3",
                "password": "pwd3",
                "enabled": True,
                "metadata": {},
                "bound_accounts": [],
            }
        ],
    )

    configs = await manager._collect_user_linyu_configs()

    assert configs == {}


@pytest.mark.asyncio
async def test_collect_linyu_configs_inherits_server_and_ignores_legacy_metadata(monkeypatch):
    manager = LinyuSessionManager(bot=object())

    monkeypatch.setattr(
        "backend.adapters.linyu_manager.config._config",
        _base_linyu_config(enabled=True),
        raising=False,
    )
    monkeypatch.setattr(
        "backend.adapters.linyu_manager.account_registry.list_linyu_ai_accounts",
        lambda enabled=None: [
            {
                "id": 1,
                "companion_name": "小雨",
                "account_name": "ai_user_1",
                "account": "ai_user_1",
                "password": "pwd1",
                "enabled": True,
                "metadata": {
                    "linyu": {
                        "http_host": "should-not-be-used.local",
                        "target_user_id": "custom-target-id",
                        "target_user_account": "custom-target-account",
                        "auto_bind_first_user": True,
                    }
                },
                "bound_accounts": [
                    {
                        "id": 11,
                        "platform": "linyu",
                        "account_name": "bound_user_1",
                        "remote_user_id": "uuid-user-1",
                        "display_name": "bound_user_1",
                        "enabled": True,
                    }
                ],
            }
        ],
    )

    configs = await manager._collect_user_linyu_configs()

    cfg = configs["companion:1"]
    assert cfg["http_host"] == "10.0.0.8"
    assert cfg["http_port"] == 9200
    assert cfg["ws_host"] == "10.0.0.8"
    assert cfg["ws_port"] == 9100
    assert cfg["_allowed_user_ids"] == ["uuid-user-1"]
    assert cfg["_target_user_id"] == "uuid-user-1"
    assert cfg["_target_display_name"] == "bound_user_1"
    assert "target_user_id" not in cfg
    assert "target_user_account" not in cfg
    assert "auto_bind_first_user" not in cfg


def test_owner_id_from_companion_session_id():
    assert (
        LinyuSessionManager._owner_id_from_session_id("linyu_private:42:550e8400-e29b-41d4-a716-446655440000")
        == "companion:42"
    )
    assert (
        LinyuSessionManager._owner_id_from_session_id("companion_session:42:linyu:550e8400-e29b-41d4-a716-446655440000")
        == "companion:42"
    )
    assert LinyuSessionManager._owner_id_from_session_id("linyu_private:550e8400-e29b-41d4-a716-446655440000") == ""
