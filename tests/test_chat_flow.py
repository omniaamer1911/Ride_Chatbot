import json

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm
from app.chatbot.providers.base import AssistantTurn, ToolCall
from app.chatbot.providers.mock_provider import MockLLMProvider


def test_chat_book_then_cancel(app):
    mock = MockLLMProvider()
    mock.enqueue(
        AssistantTurn(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_book",
                    name="book_trip",
                    arguments=json.dumps(
                        {
                            "pickup_query": "المعادي",
                            "dropoff_query": "التجمع الخامس",
                            "vehicle_type": "economy",
                        },
                        ensure_ascii=False,
                    ),
                )
            ],
        )
    )
    mock.enqueue(AssistantTurn(content="تمام يا فندم، اتأكدنا الحجز والسواق في الطريق.", tool_calls=[]))

    app.dependency_overrides[get_llm] = lambda: mock
    with TestClient(app) as client:
        r1 = client.post(
            "/api/chat",
            json={"user_id": "u_flow", "message": "احجزلي عربية اقتصادي من المعادي للتجمع الخامس"},
        )
        assert r1.status_code == 200
        body1 = r1.json()
        assert "reply_ar" in body1

        mock.enqueue(
            AssistantTurn(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_cancel",
                        name="cancel_trip",
                        arguments=json.dumps(
                            {
                                "trip_id": 1,
                                "reason": "غيرت خطتي",
                            },
                            ensure_ascii=False,
                        ),
                    )
                ],
            )
        )
        mock.enqueue(AssistantTurn(content="تم الإلغاء يا فندم.", tool_calls=[]))

        r2 = client.post(
            "/api/chat",
            json={"user_id": "u_flow", "message": "الغي الرحلة لو سمحت"},
        )
        assert r2.status_code == 200

    app.dependency_overrides.clear()
