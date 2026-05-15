import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Driver, DriverStatus
from app.services.matching import find_best_drivers


@pytest.mark.asyncio
async def test_matching_orders_by_score():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                Driver(
                    name_ar="قريب",
                    vehicle_type="economy",
                    car_make="x",
                    car_model="y",
                    plate="1",
                    rating=4.9,
                    acceptance_rate=0.99,
                    lat=30.05,
                    lng=31.24,
                    status=DriverStatus.available,
                ),
                Driver(
                    name_ar="بعيد",
                    vehicle_type="economy",
                    car_make="x",
                    car_model="y",
                    plate="2",
                    rating=4.0,
                    acceptance_rate=0.8,
                    lat=30.2,
                    lng=31.5,
                    status=DriverStatus.available,
                ),
            ]
        )
        await session.commit()
        m = await find_best_drivers(session, 30.051, 31.241, "economy", limit=2)
        assert len(m) == 2
        assert m[0].name_ar == "قريب"

    await engine.dispose()
