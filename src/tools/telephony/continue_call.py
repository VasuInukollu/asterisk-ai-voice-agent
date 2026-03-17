"""
Continue In Dialplan Tool - Exit Stasis and return the call to the Asterisk dialplan.

Allows the AI agent to hand back control to the dialplan, for example when
the caller presses * or # to reach a main menu, or when the conversation
topic requires routing through a different dialplan context.

The engine will call POST /channels/{id}/continue after the farewell audio
finishes, which exits Stasis and resumes dialplan execution at the specified
context/extension/priority.
"""

from typing import Dict, Any
from src.tools.base import Tool, ToolDefinition, ToolParameter, ToolCategory
from src.tools.context import ToolExecutionContext
import structlog

logger = structlog.get_logger(__name__)


class ContinueInDialplanTool(Tool):
    """
    Exit Stasis and return the caller to the Asterisk dialplan.

    Use when:
    - The caller presses * or # requesting the main menu
    - The conversation flow requires handing back to a dialplan extension
    - The caller explicitly asks to speak with the operator or go back

    The optional context/extension/priority parameters let you target a
    specific dialplan location; omit them to use the values configured in
    ai-agent.yaml under ``tools.continue_in_dialplan``.
    """

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="continue_in_dialplan",
            description=(
                "Exit the AI agent and return the caller to the Asterisk dialplan. "
                "Use this when the caller presses * or # to reach the main menu, "
                "or when they ask to speak with an operator or go back to the menu."
            ),
            category=ToolCategory.TELEPHONY,
            requires_channel=True,
            max_execution_time=5,
            parameters=[
                ToolParameter(
                    name="message",
                    type="string",
                    description=(
                        "Short message to speak before returning to the dialplan, "
                        "e.g. 'Returning you to the main menu now.'"
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="context",
                    type="string",
                    description="Asterisk dialplan context to continue into (e.g. 'default').",
                    required=False,
                ),
                ToolParameter(
                    name="extension",
                    type="string",
                    description="Dialplan extension to continue at (default: 's').",
                    required=False,
                ),
                ToolParameter(
                    name="priority",
                    type="integer",
                    description="Dialplan priority to continue at (default: 1).",
                    required=False,
                ),
            ],
        )

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ToolExecutionContext,
    ) -> Dict[str, Any]:
        """
        Schedule the channel to be returned to the dialplan after TTS finishes.

        Stores continue parameters on the session; the engine's TTS-done handler
        calls ``ari_client.continue_in_dialplan()`` once audio playback ends.

        Args:
            parameters: {
                message: Optional[str],
                context: Optional[str],
                extension: Optional[str],
                priority: Optional[int]
            }
            context: Tool execution context

        Returns:
            {
                status: "success" | "error",
                message: str,
                will_continue: True
            }
        """
        message = parameters.get("message") or context.get_config_value(
            "tools.continue_in_dialplan.message",
            "Returning you to the main menu.",
        )

        dialplan_context = parameters.get("context") or context.get_config_value(
            "tools.continue_in_dialplan.context",
            "default",
        )

        extension = parameters.get("extension") or context.get_config_value(
            "tools.continue_in_dialplan.extension",
            "s",
        )

        raw_priority = parameters.get("priority")
        if raw_priority is None:
            raw_priority = context.get_config_value(
                "tools.continue_in_dialplan.priority", 1
            )
        try:
            priority = int(raw_priority)
        except (TypeError, ValueError):
            priority = 1

        logger.info(
            "📞 Continue in dialplan requested",
            call_id=context.call_id,
            dialplan_context=dialplan_context,
            extension=extension,
            priority=priority,
        )

        try:
            await context.update_session(
                continue_after_tts=True,
                continue_dialplan_context=str(dialplan_context),
                continue_dialplan_extension=str(extension),
                continue_dialplan_priority=priority,
            )
            logger.info(
                "✅ Call will continue in dialplan after farewell",
                call_id=context.call_id,
                dialplan_context=dialplan_context,
                extension=extension,
                priority=priority,
            )

            return {
                "status": "success",
                "message": message,
                "will_continue": True,
            }

        except Exception as e:
            logger.error(
                "Error preparing continue in dialplan",
                call_id=context.call_id,
                error=str(e),
                exc_info=True,
            )
            return {
                "status": "error",
                "message": message,
                "will_continue": True,
                "error": str(e),
            }
