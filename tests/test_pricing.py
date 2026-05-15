from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Trip, TripStatus, User
from app.services.pricing import compute_surge, estimate_trip_price


@pytest.mark.asyncio
async def test_compute_surge_rush():
    when = datetime(2026, 5, 6, 8, 0, tzinfo=timezone.utc)
    s = compute_surge(when, active_trips=0, bad_weather=False)
    assert s >= 1.1


@pytest.mark.asyncio
async def test_estimate_price_band():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        u = User(external_id="u1")
        session.add(u)
        await session.commit()

        est = await estimate_trip_price(
            session,
            29.96,
            31.2569,
            30.0074,
            31.4913,
            base_fare=17.5,
            per_km=5.1,
            per_min=1.05,
            when=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
            bad_weather=False,
        )
        assert est.min_egp < est.max_egp
        assert est.distance_km > 0

    await engine.dispose()
