"""Map OpenAI-style message/tool payloads to Anthropic Messages API."""

from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic

from app.chatbot.providers.base import AssistantTurn, LLMProvider, ToolCall


def _openai_tools_to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in tools:
        fn = t.get("function", {})
        name = fn.get("name")
        desc = fn.get("description", "")
        params = fn.get("parameters") or {"type": "object", "properties": {}}
        out.append(
            {
                "name": name,
                "description": desc,
                "input_schema": params,
            }
        )
    return out


def _openai_messages_to_anthropic(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    system: str | None = None
    anth_msgs: list[dict[str, Any]] = []
    pending_tool_results: list[dict[str, Any]] = []

    for m in messages:
        role = m.get("role")
        if role == "system":
            system = (system or "") + (m.get("content") or "")
            continue
        if role == "user":
            if pending_tool_results:
                anth_msgs.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []
            anth_msgs.append({"role": "user", "content": m.get("content") or ""})
            continue
        if role == "assistant":
            if pending_tool_results:
                anth_msgs.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                tid = tc.get("id", "")
                name = fn.get("name", "")
                args = fn.get("arguments") or "{}"
                try:
                    parsed = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError:
                    parsed = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tid,
                        "name": name,
                        "input": parsed,
                    }
                )
            anth_msgs.append({"role": "assistant", "content": blocks})
            continue
        if role == "tool":
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": m.get("content") or "",
                }
            )
            continue

    if pending_tool_results:
        anth_msgs.append({"role": "user", "content": pending_tool_results})

    return system, anth_msgs


def _anthropic_response_to_turn(resp: Any) -> AssistantTurn:
    tcs: list[ToolCall] = []
    text_parts: list[str] = []
    for block in resp.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(getattr(block, "text", "") or "")
        elif btype == "tool_use":
            tcs.append(
                ToolCall(
                    id=getattr(block, "id", "") or "",
                    name=getattr(block, "name", "") or "",
                    arguments=json.dumps(getattr(block, "input", {}) or {}, ensure_ascii=False),
                )
            )
    content = "\n".join(text_parts).strip() or None
    return AssistantTurn(content=content, tool_calls=tcs)


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AssistantTurn:
        system, anth_msgs = _openai_messages_to_anthropic(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 2048,
            "messages": anth_msgs,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _openai_tools_to_anthropic(tools)
        resp = await self._client.messages.create(**kwargs)
        return _anthropic_response_to_turn(resp)
