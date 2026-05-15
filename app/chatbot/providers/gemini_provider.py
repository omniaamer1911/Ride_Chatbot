"""Map OpenAI-style message/tool payloads to Google Gemini generate_content API."""

from __future__ import annotations

import json
import uuid
from typing import Any

from google import genai
from google.genai import types

from app.chatbot.providers.base import AssistantTurn, LLMProvider, ToolCall


def _openai_tools_to_gemini(tools: list[dict[str, Any]]) -> list[types.Tool]:
    decls: list[types.FunctionDeclaration] = []
    for t in tools:
        fn = t.get("function", {})
        decls.append(
            types.FunctionDeclaration(
                name=fn.get("name", ""),
                description=fn.get("description", ""),
                parameters_json_schema=fn.get("parameters")
                or {"type": "object", "properties": {}},
            )
        )
    return [types.Tool(function_declarations=decls)]


def _tool_result_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"result": content}


def _openai_messages_to_gemini(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[types.Content]]:
    system: str | None = None
    contents: list[types.Content] = []
    tool_names: dict[str, str] = {}

    for m in messages:
        role = m.get("role")
        if role == "system":
            system = (system or "") + (m.get("content") or "")
            continue
        if role == "user":
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=m.get("content") or "")],
                )
            )
            continue
        if role == "assistant":
            parts: list[types.Part] = []
            if m.get("content"):
                parts.append(types.Part.from_text(text=m["content"]))
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                tid = tc.get("id") or str(uuid.uuid4())
                name = fn.get("name", "")
                tool_names[tid] = name
                args = fn.get("arguments") or "{}"
                try:
                    parsed = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError:
                    parsed = {}
                parts.append(
                    types.Part.from_function_call(name=name, args=parsed or {})
                )
            if parts:
                contents.append(types.Content(role="model", parts=parts))
            continue
        if role == "tool":
            tid = m.get("tool_call_id", "")
            name = m.get("name") or tool_names.get(tid, "")
            contents.append(
                types.Content(
                    role="tool",
                    parts=[
                        types.Part.from_function_response(
                            name=name,
                            response=_tool_result_response(m.get("content") or ""),
                        )
                    ],
                )
            )
            continue

    return system, contents


def _gemini_response_to_turn(resp: Any) -> AssistantTurn:
    tcs: list[ToolCall] = []
    text_parts: list[str] = []

    for fc in resp.function_calls or []:
        fc_id = getattr(fc, "id", None) or str(uuid.uuid4())
        args = getattr(fc, "args", None) or {}
        tcs.append(
            ToolCall(
                id=fc_id,
                name=getattr(fc, "name", "") or "",
                arguments=json.dumps(args, ensure_ascii=False),
            )
        )

    if resp.candidates:
        for part in resp.candidates[0].content.parts or []:
            if part.text:
                text_parts.append(part.text)

    content = "\n".join(text_parts).strip() or None
    return AssistantTurn(content=content, tool_calls=tcs)


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AssistantTurn:
        system, gemini_contents = _openai_messages_to_gemini(messages)
        config_kwargs: dict[str, Any] = {}
        if system:
            config_kwargs["system_instruction"] = system
        if tools:
            config_kwargs["tools"] = _openai_tools_to_gemini(tools)
            config_kwargs["automatic_function_calling"] = (
                types.AutomaticFunctionCallingConfig(disable=True)
            )
        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        kwargs: dict[str, Any] = {
            "model": self._model,
            "contents": gemini_contents,
        }
        if config is not None:
            kwargs["config"] = config

        resp = await self._client.aio.models.generate_content(**kwargs)
        return _gemini_response_to_turn(resp)
