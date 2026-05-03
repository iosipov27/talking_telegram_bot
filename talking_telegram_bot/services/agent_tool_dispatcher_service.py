from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from talking_telegram_bot.models.agent import AgentToolCall


class AgentToolExecutionError(RuntimeError):
    """Raised when an agent tool can not be completed safely."""


@dataclass(frozen=True, slots=True)
class AgentToolContext:
    correlation_id: str
    causation_id: str
    chat_id: int | None
    user_id: int | None


class AgentTool(Protocol):
    action_name: str

    async def execute(
        self,
        args: dict[str, object],
        context: AgentToolContext,
    ) -> str:
        """Run the tool and return the observation text for the agent."""


class AgentToolDispatcherService:
    def __init__(
        self,
        tools: list[AgentTool],
        timeout_seconds: float = 30.0,
    ) -> None:
        self._tools = {tool.action_name: tool for tool in tools}
        self._timeout_seconds = timeout_seconds

    def can_execute(self, action: str) -> bool:
        return action in self._tools

    async def execute_tool(
        self,
        tool_call: AgentToolCall,
        context: AgentToolContext,
    ) -> str:
        tool = self._tools.get(tool_call.action)
        if tool is None:
            raise AgentToolExecutionError(f"Unknown tool: {tool_call.action}.")
        try:
            return await asyncio.wait_for(
                tool.execute(tool_call.args, context),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise AgentToolExecutionError(
                f"Tool {tool_call.action} timed out.",
            ) from exc
        except AgentToolExecutionError:
            raise
        except Exception as exc:
            raise AgentToolExecutionError(str(exc)) from exc
