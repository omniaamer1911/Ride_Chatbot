"""Chat turn loop: DB history → LLM → tools → Arabic reply."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot.prompts import FEW_SHOT, SYSTEM_PROMPT_MASRI
from app.chatbot.providers.base import LLMProvider
from app.chatbot.tools import ToolContext, ToolDispatcher, tool_definitions_openai
from app.db.models import Message
from app.events.bus import EventBus
from app.services.geocoding import GeoProvider
from app.services.trips import get_or_create_user

logger = logging.getLogger(__name__)


def _openai_tool_calls_from_db(json_str: str | None) -> list[dict[str, Any]]:
    if not json_str:
        return []
    try:
        data = json.loads(json_str)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def messages_from_db_rows(rows: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in rows:
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            tcs = _openai_tool_calls_from_db(m.tool_calls_json)
            msg: dict[str, Any] = {"role": "assistant", "content": m.content or None}
            if tcs:
                msg["tool_calls"] = tcs
            out.append(msg)
        elif m.role == "tool":
            tool_msg: dict[str, Any] = {
                "role": "tool",
                "tool_call_id": m.tool_call_id or "",
                "content": m.content,
            }
            if m.tool_name:
                tool_msg["name"] = m.tool_name
            out.append(tool_msg)
    return out


async def load_history(session: AsyncSession, user_db_id: int, limit: int = 40) -> list[Message]:
    q = (
        select(Message)
        .where(Message.user_id == user_db_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    r = await session.execute(q)
    rows = list(r.scalars().all())
    rows.reverse()
    return rows


async def run_chat_turn(
    session: AsyncSession,
    bus: EventBus,
    geocoder: GeoProvider,
    llm: LLMProvider,
    user_external_id: str,
    user_text: str,
    max_tool_rounds: int = 8,
) -> str:
    user = await get_or_create_user(session, user_external_id)
    session.add(
        Message(
            user_id=user.id,
            role="user",
            content=user_text,
        )
    )
    await session.flush()

    history = await load_history(session, user.id)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                SYSTEM_PROMPT_MASRI
                + f"\n- جلسة المستخدم الحالية (من التطبيق): {user_external_id!r}."
            ),
        }
    ]
    messages.extend(FEW_SHOT)
    messages.extend(messages_from_db_rows(history))

    tools = tool_definitions_openai()
    dispatcher = ToolDispatcher(
        ToolContext(
            session=session,
            bus=bus,
            geocoder=geocoder,
            user_external_id=user_external_id,
        )
    )

    for _ in range(max_tool_rounds):
        turn = await llm.chat(messages, tools)
        if turn.tool_calls:
            tc_payload = []
            assistant_tool_calls = []
            for tc in turn.tool_calls:
                assistant_tool_calls.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                )
                tc_payload.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                )
            session.add(
                Message(
                    user_id=user.id,
                    role="assistant",
                    content=turn.content or "",
                    tool_calls_json=json.dumps(tc_payload, ensure_ascii=False),
                )
            )
            await session.flush()

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "tool_calls": assistant_tool_calls,
                "content": turn.content if turn.content else None,
            }
            messages.append(assistant_msg)

            for tc in turn.tool_calls:
                result = await dispatcher.dispatch(tc.name, tc.arguments)
                try:
                    payload = json.loads(result)
                    if payload.get("ok") is False:
                        logger.warning(
                            "Tool %s returned error for user %s: %s",
                            tc.name,
                            user_external_id,
                            payload.get("error_ar"),
                        )
                except json.JSONDecodeError:
                    logger.warning(
                        "Tool %s returned non-JSON for user %s: %s",
                        tc.name,
                        user_external_id,
                        result[:200],
                    )
                session.add(
                    Message(
                        user_id=user.id,
                        role="tool",
                        content=result,
                        tool_name=tc.name,
                        tool_call_id=tc.id,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result,
                    }
                )
            await session.flush()
            continue

        text = (turn.content or "").strip() or "تمام يا فندم."
        session.add(
            Message(
                user_id=user.id,
                role="assistant",
                content=text,
            )
        )
        await session.flush()
        return text

    return "في حملة أدوات طويلة أوي؛ جرّب تبسّط الطلب يا فندم."
