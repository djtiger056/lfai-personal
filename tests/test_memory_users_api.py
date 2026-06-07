import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.accounts import AccountRegistry
from backend.api.memory import get_memory_users, _ensure_session_access, _ensure_user_id_access
from backend.memory import MemoryConfig, MemoryManager
from backend.memory.models import ConversationMessage
from backend.utils.datetime_utils import get_now


def _build_registry(tmp_path: Path) -> AccountRegistry:
    registry = AccountRegistry(tmp_path / "accounts.db")
    alice = registry.upsert_account(
        platform="linyu",
        account_name="alice",
        remote_user_id="550e8400-e29b-41d4-a716-446655440000",
        display_name="Alice",
        enabled=True,
    )
    bob = registry.upsert_account(
        platform="linyu",
        account_name="bob",
        remote_user_id="660e8400-e29b-41d4-a716-446655440000",
        display_name="Bob",
        enabled=True,
    )
    registry.upsert_account(
        platform="linyu",
        account_name="charlie",
        remote_user_id="770e8400-e29b-41d4-a716-446655440000",
        display_name="Charlie",
        enabled=True,
    )
    registry.upsert_account(
        platform="qq",
        account_name="123456",
        remote_user_id="123456",
        display_name="QQ用户",
        enabled=True,
    )
    registry.upsert_linyu_ai_account(
        account_name="ai-rain",
        companion_name="小雨",
        password="pw",
        enabled=True,
        bound_account_ids=[alice["id"], bob["id"]],
    )
    registry.upsert_linyu_ai_account(
        account_name="ai-snow",
        companion_name="小雪",
        password="pw",
        enabled=True,
        bound_account_ids=[alice["id"]],
    )
    return registry


@pytest.mark.asyncio
async def test_get_memory_users_returns_companion_scoped_linyu_identities(monkeypatch, tmp_path):
    registry = _build_registry(tmp_path)
    monkeypatch.setattr("backend.api.memory.account_registry", registry)
    monkeypatch.setattr("backend.api.memory._get_stored_memory_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "backend.api.memory._get_authenticated_user",
        AsyncMock(return_value={"personal": True}),
    )

    result = await get_memory_users(token="valid-token")

    assert result["user_ids"] == [
        "web_user",
        "123456",
        "companion:1",
        "companion:2",
    ]
    assert result["user_info"][:2] == [
        {
            "user_id": "web_user",
            "display_name": "Web 控制台",
            "selector_key": "Web 控制台",
            "channel": "web",
            "default_session_id": "web_user",
            "memory_user_id": "web_user",
            "memory_session_id": "web_user",
            "remote_user_id": "",
            "project_user_id": "web_user",
        },
        {
            "user_id": "123456",
            "display_name": "QQ:QQ用户",
            "selector_key": "qq:123456",
            "channel": "qq",
            "default_session_id": "123456",
            "memory_user_id": "123456",
            "memory_session_id": "123456",
            "remote_user_id": "123456",
            "project_user_id": "123456",
        },
    ]

    linyu_entries = [item for item in result["user_info"] if item["channel"] == "linyu"]
    assert [item["display_name"] for item in linyu_entries] == [
        "小雨 | Linyu:ai-rain | 绑定:Alice、Bob",
        "小雪 | Linyu:ai-snow | 绑定:Alice",
    ]
    assert [item["memory_user_id"] for item in linyu_entries] == [
        "companion:1",
        "companion:2",
    ]
    assert [item["memory_session_id"] for item in linyu_entries] == [
        "companion_memory:1",
        "companion_memory:2",
    ]
    assert [item["source_session_ids"] for item in linyu_entries] == [
        [
            "companion_session:1:linyu:550e8400-e29b-41d4-a716-446655440000",
            "companion_session:1:linyu:660e8400-e29b-41d4-a716-446655440000",
        ],
        [
            "companion_session:2:linyu:550e8400-e29b-41d4-a716-446655440000",
        ],
    ]
    assert all(item.get("remote_user_id") == "" for item in linyu_entries)


@pytest.mark.asyncio
async def test_get_memory_users_requires_valid_token(monkeypatch):
    monkeypatch.setattr(
        "backend.api.memory._get_authenticated_user",
        AsyncMock(side_effect=HTTPException(status_code=401, detail="无效的令牌")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_memory_users(token="bad-token")

    assert exc_info.value.status_code == 401


def test_memory_access_accepts_companion_user_and_companion_session(monkeypatch, tmp_path):
    registry = _build_registry(tmp_path)
    monkeypatch.setattr("backend.api.memory.account_registry", registry)
    monkeypatch.setattr("backend.api.memory._get_stored_memory_entries", lambda *_args, **_kwargs: [])

    user = {"personal": True}
    assert _ensure_user_id_access(user, "companion:1") == "companion:1"
    assert _ensure_session_access(
        user,
        "companion_memory:1",
    ) == "companion_memory:1"
    assert _ensure_session_access(
        user,
        "companion_session:2:linyu:550e8400-e29b-41d4-a716-446655440000",
    ) == "companion_session:2:linyu:550e8400-e29b-41d4-a716-446655440000"


def test_memory_access_rejects_unbound_linyu_session(monkeypatch, tmp_path):
    registry = _build_registry(tmp_path)
    monkeypatch.setattr("backend.api.memory.account_registry", registry)
    monkeypatch.setattr("backend.api.memory._get_stored_memory_entries", lambda *_args, **_kwargs: [])

    with pytest.raises(HTTPException) as exc_info:
        _ensure_session_access(
            {"personal": True},
            "companion_session:1:linyu:770e8400-e29b-41d4-a716-446655440000",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_companion_memory_scope_merges_cross_platform_sessions(tmp_path):
    manager = MemoryManager(MemoryConfig())
    manager.db_url = f"sqlite+aiosqlite:///{(tmp_path / 'memory.db').as_posix()}"
    await manager.initialize()

    await manager.add_short_term_memory(
        "companion:1",
        "companion_session:1:linyu:550e8400-e29b-41d4-a716-446655440000",
        ConversationMessage(role="user", content="linyu hello", timestamp=get_now()),
    )
    await manager.add_short_term_memory(
        "companion:1",
        "companion_session:1:qq:123456",
        ConversationMessage(role="assistant", content="qq hi", timestamp=get_now()),
    )

    memories = await manager.get_short_term_memories("companion:1", "companion_memory:1", limit=10)
    assert [item["message"]["content"] for item in memories] == ["linyu hello", "qq hi"]
