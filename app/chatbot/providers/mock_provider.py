from __future__ import annotations

from collections import deque
from typing import Any

from app.chatbot.providers.base import AssistantTurn, LLMProvider, ToolCall


class MockLLMProvider(LLMProvider):
    """Deterministic scripted turns for tests."""

    def __init__(self, turns: list[AssistantTurn] | None = None) -> None:
        self._q: deque[AssistantTurn] = deque(turns or [])

    def enqueue(self, turn: AssistantTurn) -> None:
        self._q.append(turn)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AssistantTurn:
        if not self._q:
            return AssistantTurn(content="(mock: empty queue)", tool_calls=[])
        return self._q.popleft()
