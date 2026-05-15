import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.drivers import router as drivers_router
from app.api.trips import router as trips_router
from app.api.ws import router as ws_router
from app.db.seed import seed_if_empty
from app.db.session import async_session_factory, init_db
from app.events.bus import EventBus
from app.services.geocoding import LandmarkGeocoder
from app.services.simulator import simulator_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    bus = EventBus()
    geocoder = LandmarkGeocoder()
    app.state.bus = bus
    app.state.geocoder = geocoder

    factory = async_session_factory()
    async with factory() as session:
        await seed_if_empty(session)
        await session.commit()

    stop = asyncio.Event()
    app.state.sim_stop = stop
    app.state.sim_task = asyncio.create_task(simulator_loop(stop, bus))

    yield

    stop.set()
    app.state.sim_task.cancel()
    try:
        await app.state.sim_task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    app = FastAPI(title="Ride Chatbot Egypt", lifespan=lifespan)
    app.include_router(chat_router)
    app.include_router(trips_router)
    app.include_router(drivers_router)
    app.include_router(ws_router)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


app = create_app()
