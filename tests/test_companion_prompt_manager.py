from types import SimpleNamespace

import pytest

import backend.prompt_system.manager as prompt_manager_module
import backend.core.user_cache as user_cache_module
from backend.prompt_system.manager import PromptManager
from backend.accounts import AccountRegistry
from backend.api import prompt as prompt_api
from backend.core.bot import Bot


def test_companion_prompts_are_isolated_and_fallback_to_global(monkeypatch, tmp_path):
    prompts_dir = tmp_path / "prompts"
    monkeypatch.setattr(prompt_manager_module, "PERSONAL_PROMPTS_DIR", prompts_dir)
    monkeypatch.setattr(prompt_manager_module, "ensure_personal_dirs", lambda: prompts_dir.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(prompt_manager_module, "config", SimpleNamespace(system_prompt="全局默认人设"))

    manager = PromptManager()

    assert manager.get_effective_prompt("companion:1") == "全局默认人设"
    assert manager.get_effective_prompt("companion:2") == "全局默认人设"

    assert manager.set_prompt("companion:1", "小雨的人设", source="user", summary="init") is True
    assert manager.set_prompt("companion:2", "小雪的人设", source="user", summary="init") is True

    assert manager.get_effective_prompt("companion:1") == "小雨的人设"
    assert manager.get_effective_prompt("companion:2") == "小雪的人设"
    assert (prompts_dir / "companions" / "companion_1" / "system_prompt.md").read_text(encoding="utf-8") == "小雨的人设"
    assert (prompts_dir / "companions" / "companion_2" / "system_prompt.md").read_text(encoding="utf-8") == "小雪的人设"

    assert manager.delete_prompt("companion:1") is True
    assert manager.get_effective_prompt("companion:1") == "全局默认人设"
    assert manager.get_effective_prompt("companion:2") == "小雪的人设"


def test_prompt_api_normalizes_legacy_linyu_companion_id(monkeypatch, tmp_path):
    prompts_dir = tmp_path / "prompts"
    registry = AccountRegistry(tmp_path / "accounts.db")
    companion = registry.upsert_linyu_ai_account(
        account_name="bot-rain",
        companion_name="小雨",
        password="pw",
        remote_user_id="bot-uuid",
        enabled=True,
    )
    with registry._connect() as conn:
        conn.execute(
            """
            INSERT INTO linyu_ai_accounts(
                id, companion_name, account_name, account, password, remote_user_id,
                enabled, metadata, created_at, updated_at
            )
            VALUES (3, '小雨', 'bot-rain', 'bot-rain', 'pw', 'bot-uuid',
                    1, '{}', '2026-01-01T00:00:00+08:00', '2026-01-01T00:00:00+08:00')
            """
        )

    monkeypatch.setattr(prompt_manager_module, "PERSONAL_PROMPTS_DIR", prompts_dir)
    monkeypatch.setattr(prompt_manager_module, "ensure_personal_dirs", lambda: prompts_dir.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(prompt_api, "account_registry", registry)

    resolved = prompt_api._resolve_companion_prompt_id("companion:linyu:3")
    assert resolved == f"companion:{companion['id']}"

    prompt_manager_module.prompt_manager.set_prompt(resolved, "旧ID写入也应落到当前伴侣")

    assert (prompts_dir / "companions" / f"companion_{companion['id']}" / "system_prompt.md").read_text(encoding="utf-8") == "旧ID写入也应落到当前伴侣"
    assert not (prompts_dir / "companions" / "companion_linyu_3" / "system_prompt.md").exists()


@pytest.mark.asyncio
async def test_bot_context_uses_companion_specific_prompt(monkeypatch, tmp_path):
    prompts_dir = tmp_path / "prompts"
    monkeypatch.setattr(prompt_manager_module, "PERSONAL_PROMPTS_DIR", prompts_dir)
    monkeypatch.setattr(prompt_manager_module, "ensure_personal_dirs", lambda: prompts_dir.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(prompt_manager_module, "config", SimpleNamespace(system_prompt="全局默认人设", system_rules=""))

    manager = PromptManager()
    assert manager.set_prompt("companion:1", "栗子专属人设", source="user") is True
    assert manager.set_prompt("companion:2", "小馨专属人设", source="user") is True
    monkeypatch.setattr(prompt_manager_module, "prompt_manager", manager)
    monkeypatch.setattr(user_cache_module, "prompt_manager", manager)

    bot = Bot.__new__(Bot)
    bot._user_cache = user_cache_module.UserResourceCache()
    bot._context_builder = __import__("backend.core.context_builder", fromlist=["ContextBuilder"]).ContextBuilder(bot)
    bot.mcp_manager = None
    bot.memory_manager = None
    bot._video_intent_sessions = {}
    bot._get_user_config = lambda user_id: {}
    bot._build_long_gap_repeat_hint = lambda history, message: ""
    bot._build_companion_mode_hint = lambda session_id, history, message: ""
    bot._append_mid_term_context = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock()
    bot._build_video_generation_hint = lambda user_id, session_id, message: ""
    bot._build_memory_context = lambda relevant_memories, history, limit=3: ""

    history = [{"role": "system", "content": bot._user_cache.get_system_prompt("companion:1")}]
    result = await bot._context_builder.build(
        message="你好",
        user_id="companion:1",
        session_id="companion_session:1:linyu:user-a",
        history=history,
        relevant_memories=[],
    )

    assert result.history_messages == []
    assert result.dynamic_blocks == []
    assert bot._user_cache.get_system_prompt("companion:1") == "栗子专属人设"
    assert manager.get_effective_prompt("companion:2") == "小馨专属人设"
