import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Driver, DriverStatus, Vehicle
from app.events.bus import EventBus
from app.services.geocoding import LandmarkGeocoder
from app.chatbot.tools import ToolContext, ToolDispatcher


@pytest.mark.asyncio
async def test_resolve_location_tool():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Vehicle(
                type_key="economy",
                name_ar="اقتصادي",
                base_fare=17.5,
                per_km=5.1,
                per_min=1.05,
            )
        )
        session.add(
            Driver(
                name_ar="س",
                vehicle_type="economy",
                car_make="t",
                car_model="c",
                plate="99",
                rating=4.8,
                acceptance_rate=0.95,
                lat=30.0444,
                lng=31.2357,
                status=DriverStatus.available,
            )
        )
        await session.commit()
        d = ToolDispatcher(
            ToolContext(session=session, bus=EventBus(), geocoder=LandmarkGeocoder())
        )
        out = await d.dispatch("resolve_location", json.dumps({"query": "التحرير"}))
        data = json.loads(out)
        assert data["ok"] is True

        out2 = await d.dispatch(
            "estimate_price",
            json.dumps(
                {
                    "pickup_query": "ميدان التحرير",
                    "dropoff_query": "مدينة نصر",
                    "vehicle_type": "economy",
                }
            ),
        )
        data2 = json.loads(out2)
        assert data2["ok"] is True
        assert data2["min_egp"] < data2["max_egp"]

    await engine.dispose()
