import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

from app.api.chat import router as chat_router
from app.api.drivers import router as drivers_router
from app.api.trips import router as trips_router
from app.db.seed import seed_if_empty
from app.db.session import async_session_factory, init_db
from app.services.geocoding import LandmarkGeocoder


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    geocoder = LandmarkGeocoder()
    app.state.geocoder = geocoder

    factory = async_session_factory()
    async with factory() as session:
        await seed_if_empty(session)
        await session.commit()

    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Ride Chatbot Egypt", lifespan=lifespan)
    app.include_router(chat_router)
    app.include_router(trips_router)
    app.include_router(drivers_router)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


app = create_app()
