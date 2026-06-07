import pytest

from backend.prompt_assembly import PromptAssembler, PromptBlueprint, PromptBlock


def test_prompt_assembly_renders_fixed_sections_in_order():
    assembler = PromptAssembler()
    rendered = assembler.render_messages(
        PromptBlueprint(name="test_blueprint"),
        [
            PromptBlock("persona", "system", "identity", "static", "长期角色设定", "你是测试角色。"),
            PromptBlock("rules", "system", "behavior", "static", "回复原则", "- 简洁\n- 直接"),
            PromptBlock("cap", "system", "capability", "static", "系统能力边界", "- 可使用委派"),
            PromptBlock("ctx", "user", "context", "turn", "实时上下文", "- 现在是晚上"),
            PromptBlock("task", "user", "task", "turn", "任务说明", "请回复用户。"),
            PromptBlock("input", "user", "input", "turn", "当前输入", "你好呀"),
        ],
    )

    assert len(rendered.messages) == 3
    assert rendered.messages[0]["role"] == "system"
    assert "【角色身份】" in rendered.messages[0]["content"]
    assert "【行为规则】" in rendered.messages[0]["content"]
    assert rendered.messages[1]["role"] == "system"
    assert "【能力与协议】" in rendered.messages[1]["content"]
    assert rendered.messages[2]["role"] == "user"
    assert rendered.messages[2]["content"].index("【补充上下文】") < rendered.messages[2]["content"].index("【当前任务】")
    assert rendered.messages[2]["content"].index("【当前任务】") < rendered.messages[2]["content"].index("【用户输入】")


def test_prompt_assembly_trace_is_stable_when_only_turn_input_changes():
    assembler = PromptAssembler()
    blueprint = PromptBlueprint(name="stable_trace_test")
    base_blocks = [
        PromptBlock("persona", "system", "identity", "static", "长期角色设定", "你是测试角色。"),
        PromptBlock("rules", "system", "behavior", "static", "回复原则", "- 简洁"),
        PromptBlock("cap", "system", "capability", "static", "系统能力边界", "- 无"),
    ]

    first = assembler.render_messages(
        blueprint,
        [*base_blocks, PromptBlock("input", "user", "input", "turn", "当前输入", "你好")],
    )
    second = assembler.render_messages(
        blueprint,
        [*base_blocks, PromptBlock("input", "user", "input", "turn", "当前输入", "晚安")],
    )

    assert first.trace["static_prefix_hash"] == second.trace["static_prefix_hash"]
    assert first.trace["full_prompt_hash"] != second.trace["full_prompt_hash"]


@pytest.mark.asyncio
async def test_context_builder_returns_turn_blocks_without_polluting_system(monkeypatch):
    from backend.core.context_builder import ContextBuilder

    class DummyBot:
        mcp_manager = None

        def _build_long_gap_repeat_hint(self, history, message):
            return "这是长间隔提醒"

        def _build_companion_mode_hint(self, session_id, history, message):
            return "这是陪伴提示"

        async def _collect_mid_term_context(self, user_id, session_id):
            return "这是中期摘要"

        def _build_memory_context(self, relevant_memories, history, limit=3):
            return "这是长期记忆"

        def _build_video_generation_hint(self, user_id, session_id, message):
            return "这是视频提示"

    builder = ContextBuilder(DummyBot())
    result = await builder.build(
        message="你好",
        user_id="u1",
        session_id="s1",
        history=[{"role": "user", "content": "之前聊过", "timestamp": "2026-06-07T10:00:00+08:00"}],
        relevant_memories=[{"content": "记忆1"}],
    )

    titles = [block.title for block in result.dynamic_blocks]
    assert "回答方式提醒" in titles
    assert "关系表达提醒" in titles
    assert "中期回顾" in titles
    assert "长期记忆" in titles
    assert "临时任务提示" in titles
