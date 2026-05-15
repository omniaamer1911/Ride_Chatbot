from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.chatbot.providers.base import AssistantTurn, LLMProvider, ToolCall


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AssistantTurn:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = await self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        tcs: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tcs.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments or "{}",
                    )
                )
        return AssistantTurn(content=msg.content, tool_calls=tcs)
