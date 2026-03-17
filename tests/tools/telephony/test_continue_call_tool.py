"""
Unit tests for ContinueInDialplanTool.

Tests continue-in-dialplan functionality including:
- Default and custom message handling
- Dialplan context/extension/priority parameters
- Session state updates (continue_after_tts flag)
- Config value fallback
- Error handling
"""

import pytest
from unittest.mock import AsyncMock
from src.tools.telephony.continue_call import ContinueInDialplanTool


class TestContinueInDialplanTool:
    """Test suite for the continue-in-dialplan tool."""

    @pytest.fixture
    def continue_tool(self):
        """Create ContinueInDialplanTool instance."""
        return ContinueInDialplanTool()

    # ==================== Definition Tests ====================

    def test_definition_name(self, continue_tool):
        assert continue_tool.definition.name == "continue_in_dialplan"

    def test_definition_category(self, continue_tool):
        assert continue_tool.definition.category.value == "telephony"

    def test_definition_requires_channel(self, continue_tool):
        assert continue_tool.definition.requires_channel is True

    def test_definition_max_execution_time(self, continue_tool):
        assert continue_tool.definition.max_execution_time == 5

    def test_definition_has_expected_parameters(self, continue_tool):
        param_names = [p.name for p in continue_tool.definition.parameters]
        assert "message" in param_names
        assert "context" in param_names
        assert "extension" in param_names
        assert "priority" in param_names

    def test_all_parameters_are_optional(self, continue_tool):
        for param in continue_tool.definition.parameters:
            assert param.required is False, f"Parameter {param.name!r} should be optional"

    def test_description_mentions_dialplan(self, continue_tool):
        desc = continue_tool.definition.description.lower()
        assert "dialplan" in desc or "menu" in desc

    # ==================== Execution Tests ====================

    @pytest.mark.asyncio
    async def test_continue_with_custom_message(self, continue_tool, tool_context):
        result = await continue_tool.execute(
            parameters={"message": "Heading back to the main menu!"},
            context=tool_context,
        )
        assert result["status"] == "success"
        assert result["will_continue"] is True
        assert result["message"] == "Heading back to the main menu!"

    @pytest.mark.asyncio
    async def test_continue_with_default_message(self, continue_tool, tool_context):
        result = await continue_tool.execute(parameters={}, context=tool_context)
        assert result["status"] == "success"
        assert result["will_continue"] is True
        assert len(result["message"]) > 0

    @pytest.mark.asyncio
    async def test_continue_sets_will_continue_true(self, continue_tool, tool_context):
        result = await continue_tool.execute(parameters={}, context=tool_context)
        assert result["will_continue"] is True

    @pytest.mark.asyncio
    async def test_continue_does_not_call_ari_directly(
        self, continue_tool, tool_context, mock_ari_client
    ):
        """The tool must NOT call ARI directly; the engine handles that after TTS."""
        await continue_tool.execute(parameters={}, context=tool_context)
        mock_ari_client.continue_in_dialplan.assert_not_called()

    # ==================== Session State Tests ====================

    @pytest.mark.asyncio
    async def test_sets_continue_after_tts_on_session(
        self, continue_tool, tool_context, mock_session_store, sample_call_session
    ):
        mock_session_store.get_by_call_id.return_value = sample_call_session
        await continue_tool.execute(parameters={}, context=tool_context)
        assert sample_call_session.continue_after_tts is True

    @pytest.mark.asyncio
    async def test_sets_custom_context_on_session(
        self, continue_tool, tool_context, mock_session_store, sample_call_session
    ):
        mock_session_store.get_by_call_id.return_value = sample_call_session
        await continue_tool.execute(
            parameters={"context": "ivr-menu"}, context=tool_context
        )
        assert sample_call_session.continue_dialplan_context == "ivr-menu"

    @pytest.mark.asyncio
    async def test_sets_custom_extension_on_session(
        self, continue_tool, tool_context, mock_session_store, sample_call_session
    ):
        mock_session_store.get_by_call_id.return_value = sample_call_session
        await continue_tool.execute(
            parameters={"extension": "1000"}, context=tool_context
        )
        assert sample_call_session.continue_dialplan_extension == "1000"

    @pytest.mark.asyncio
    async def test_sets_custom_priority_on_session(
        self, continue_tool, tool_context, mock_session_store, sample_call_session
    ):
        mock_session_store.get_by_call_id.return_value = sample_call_session
        await continue_tool.execute(
            parameters={"priority": 3}, context=tool_context
        )
        assert sample_call_session.continue_dialplan_priority == 3

    @pytest.mark.asyncio
    async def test_priority_string_coerced_to_int(
        self, continue_tool, tool_context, mock_session_store, sample_call_session
    ):
        mock_session_store.get_by_call_id.return_value = sample_call_session
        await continue_tool.execute(
            parameters={"priority": "2"}, context=tool_context
        )
        assert sample_call_session.continue_dialplan_priority == 2

    @pytest.mark.asyncio
    async def test_invalid_priority_falls_back_to_one(
        self, continue_tool, tool_context, mock_session_store, sample_call_session
    ):
        mock_session_store.get_by_call_id.return_value = sample_call_session
        await continue_tool.execute(
            parameters={"priority": "bad"}, context=tool_context
        )
        assert sample_call_session.continue_dialplan_priority == 1

    # ==================== Config Fallback Tests ====================

    @pytest.mark.asyncio
    async def test_message_from_config(
        self, continue_tool, mock_ari_client, mock_session_store, sample_call_session
    ):
        from src.tools.context import ToolExecutionContext

        config = {
            "tools": {
                "continue_in_dialplan": {
                    "message": "Please hold while we transfer you.",
                    "context": "cfg-context",
                    "extension": "cfg-ext",
                    "priority": 2,
                }
            }
        }
        ctx = ToolExecutionContext(
            ari_client=mock_ari_client,
            session_store=mock_session_store,
            config=config,
            call_id="test_call_123",
            caller_channel_id="PJSIP/caller-00000001",
        )
        mock_session_store.get_by_call_id.return_value = sample_call_session

        result = await continue_tool.execute(parameters={}, context=ctx)

        assert result["message"] == "Please hold while we transfer you."
        assert sample_call_session.continue_dialplan_context == "cfg-context"
        assert sample_call_session.continue_dialplan_extension == "cfg-ext"
        assert sample_call_session.continue_dialplan_priority == 2

    @pytest.mark.asyncio
    async def test_parameter_overrides_config(
        self, continue_tool, mock_ari_client, mock_session_store, sample_call_session
    ):
        """Explicit parameters should override config-level defaults."""
        from src.tools.context import ToolExecutionContext

        config = {
            "tools": {
                "continue_in_dialplan": {
                    "context": "cfg-context",
                    "extension": "s",
                    "priority": 1,
                }
            }
        }
        ctx = ToolExecutionContext(
            ari_client=mock_ari_client,
            session_store=mock_session_store,
            config=config,
            call_id="test_call_123",
            caller_channel_id="PJSIP/caller-00000001",
        )
        mock_session_store.get_by_call_id.return_value = sample_call_session

        await continue_tool.execute(
            parameters={"context": "override-context", "extension": "1234", "priority": 5},
            context=ctx,
        )

        assert sample_call_session.continue_dialplan_context == "override-context"
        assert sample_call_session.continue_dialplan_extension == "1234"
        assert sample_call_session.continue_dialplan_priority == 5

    # ==================== Error Handling Tests ====================

    @pytest.mark.asyncio
    async def test_continue_handles_missing_session(
        self, continue_tool, tool_context, mock_session_store
    ):
        mock_session_store.get_by_call_id.return_value = None

        result = await continue_tool.execute(parameters={}, context=tool_context)

        # Session not found raises RuntimeError inside update_session → caught as error
        assert result["status"] == "error"
        assert result["will_continue"] is True

    @pytest.mark.asyncio
    async def test_continue_handles_session_store_error(
        self, continue_tool, tool_context, mock_session_store
    ):
        mock_session_store.get_by_call_id.side_effect = RuntimeError("store failure")

        result = await continue_tool.execute(parameters={}, context=tool_context)

        assert result["will_continue"] is True
        assert "error" in result

    # ==================== Schema Serialisation Tests ====================

    def test_to_openai_schema(self, continue_tool):
        schema = continue_tool.definition.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "continue_in_dialplan"
        props = schema["function"]["parameters"]["properties"]
        assert "message" in props
        assert "context" in props
        assert "extension" in props
        assert "priority" in props

    def test_to_deepgram_schema(self, continue_tool):
        schema = continue_tool.definition.to_deepgram_schema()
        assert schema["name"] == "continue_in_dialplan"
        assert "parameters" in schema
