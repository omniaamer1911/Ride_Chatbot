"""Rank drivers by proximity, rating, and acceptance."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Driver, DriverStatus
from app.services.geo_utils import haversine_km, road_eta_minutes


@dataclass
class DriverMatch:
    driver_id: int
    name_ar: str
    vehicle_type: str
    car_make: str
    car_model: str
    plate: str
    rating: float
    distance_km: float
    eta_pickup_minutes: float
    score: float


def _score(distance_km: float, rating: float, acceptance: float) -> float:
    w1, w2, w3 = 0.45, 0.35, 0.20
    prox = 1.0 / (1.0 + distance_km)
    return w1 * prox + w2 * (rating / 5.0) + w3 * acceptance


async def find_best_drivers(
    session: AsyncSession,
    pickup_lat: float,
    pickup_lng: float,
    vehicle_type: str,
    limit: int = 3,
) -> list[DriverMatch]:
    q = select(Driver).where(
        Driver.status == DriverStatus.available,
        Driver.vehicle_type == vehicle_type,
    )
    res = await session.execute(q)
    drivers = list(res.scalars().all())
    ranked: list[DriverMatch] = []
    for d in drivers:
        dist = haversine_km(pickup_lat, pickup_lng, d.lat, d.lng)
        eta = road_eta_minutes(dist, avg_kmh_city=32.0, detour_factor=1.2)
        sc = _score(dist, d.rating, d.acceptance_rate)
        ranked.append(
            DriverMatch(
                driver_id=d.id,
                name_ar=d.name_ar,
                vehicle_type=d.vehicle_type,
                car_make=d.car_make,
                car_model=d.car_model,
                plate=d.plate,
                rating=d.rating,
                distance_km=round(dist, 3),
                eta_pickup_minutes=round(eta, 1),
                score=round(sc, 4),
            )
        )
    ranked.sort(key=lambda x: x.score, reverse=True)
    return ranked[:limit]
