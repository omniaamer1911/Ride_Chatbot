from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bus, get_geocoder, get_llm, get_session
from app.chatbot.engine import run_chat_turn
from app.chatbot.providers.base import LLMProvider
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    body: ChatRequest,
    session: AsyncSession = Depends(get_session),
    bus=Depends(get_bus),
    geocoder=Depends(get_geocoder),
    llm: LLMProvider = Depends(get_llm),
) -> ChatResponse:
    reply = await run_chat_turn(
        session,
        bus,
        geocoder,
        llm,
        body.user_id,
        body.message,
    )
    return ChatResponse(reply_ar=reply)
