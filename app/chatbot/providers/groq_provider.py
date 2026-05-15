from __future__ import annotations

import json
import re
import uuid
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from app.chatbot.providers.base import AssistantTurn, LLMProvider, ToolCall

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_MAX_TOOL_RETRIES = 3
_MALFORMED_TOOL_RE = re.compile(
    r"<function=(\w+)(\{.*?\})</function>",
    re.DOTALL,
)


def _parse_failed_generation(text: str) -> list[ToolCall]:
    """Salvage tool calls when Groq rejects Llama-style text output."""
    tcs: list[ToolCall] = []
    for match in _MALFORMED_TOOL_RE.finditer(text):
        name, args_str = match.group(1), match.group(2)
        try:
            json.loads(args_str)
        except json.JSONDecodeError:
            continue
        tcs.append(
            ToolCall(
                id=f"call_{uuid.uuid4().hex[:12]}",
                name=name,
                arguments=args_str,
            )
        )
    return tcs


def _tool_use_failed_generation(exc: BadRequestError) -> str | None:
    body = exc.body
    if not isinstance(body, dict):
        return None
    err = body.get("error")
    if not isinstance(err, dict):
        return None
    if err.get("code") != "tool_use_failed":
        return None
    failed = err.get("failed_generation")
    return failed if isinstance(failed, str) else None


def _response_to_turn(msg: Any) -> AssistantTurn:
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


class GroqProvider(LLMProvider):
    """Groq chat completions (OpenAI-compatible API)."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
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

        temperature = 0.6 if tools else 1.0

        for attempt in range(_MAX_TOOL_RETRIES):
            try:
                resp = await self._client.chat.completions.create(
                    **kwargs,
                    temperature=temperature,
                )
                return _response_to_turn(resp.choices[0].message)
            except BadRequestError as exc:
                failed_text = _tool_use_failed_generation(exc)
                if failed_text and tools:
                    salvaged = _parse_failed_generation(failed_text)
                    if salvaged:
                        return AssistantTurn(content=None, tool_calls=salvaged)
                if attempt < _MAX_TOOL_RETRIES - 1 and tools:
                    temperature = max(temperature - 0.2, 0.1)
                    continue
                raise

        raise RuntimeError("Groq tool call failed after retries")
