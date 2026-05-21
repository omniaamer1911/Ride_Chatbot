from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot.providers import get_llm_provider
from app.chatbot.providers.base import LLMProvider
from app.db.session import async_session_factory
from app.services.geocoding import GeoProvider


def get_llm() -> LLMProvider:
    try:
        return get_llm_provider()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_geocoder(request: Request) -> GeoProvider:
    return request.app.state.geocoder
