"""Dynamic EGP pricing: base + km + min + surge bands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Trip, TripStatus
from app.services.geo_utils import haversine_km, road_eta_minutes


@dataclass
class PriceEstimate:
    min_egp: float
    max_egp: float
    surge_factor: float
    distance_km: float
    eta_minutes: float
    breakdown: dict[str, float]


def _hour_local(dt: datetime | None) -> int:
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).hour  # simplified: use UTC hour for surge demo


def compute_surge(
    when: datetime | None,
    active_trips: int,
    bad_weather: bool,
) -> float:
    h = _hour_local(when)
    surge = 1.0
    if 7 <= h < 10 or 16 <= h < 20:
        surge *= 1.15
    if 0 <= h < 5:
        surge *= 1.12
    if bad_weather:
        surge *= 1.08
    settings = get_settings()
    if active_trips >= settings.demand_surge_threshold:
        steps = min(5, active_trips - settings.demand_surge_threshold + 1)
        surge *= 1.0 + 0.03 * steps
    return round(min(surge, 2.5), 3)


async def count_active_trips(session: AsyncSession) -> int:
    active = (
        TripStatus.requested,
        TripStatus.assigned,
        TripStatus.driver_en_route,
        TripStatus.arrived,
        TripStatus.in_progress,
    )
    q = select(func.count()).select_from(Trip).where(Trip.status.in_(active))
    n = await session.scalar(q)
    return int(n or 0)


async def estimate_trip_price(
    session: AsyncSession,
    pickup_lat: float,
    pickup_lng: float,
    dropoff_lat: float,
    dropoff_lng: float,
    base_fare: float,
    per_km: float,
    per_min: float,
    when: datetime | None = None,
    bad_weather: bool = False,
) -> PriceEstimate:
    km = haversine_km(pickup_lat, pickup_lng, dropoff_lat, dropoff_lng)
    eta = road_eta_minutes(km)
    active = await count_active_trips(session)
    surge = compute_surge(when, active, bad_weather)
    raw = (base_fare + per_km * km + per_min * eta) * surge
    band = max(8.0, raw * 0.06)
    return PriceEstimate(
        min_egp=round(max(15.0, raw - band), 2),
        max_egp=round(raw + band, 2),
        surge_factor=surge,
        distance_km=round(km, 3),
        eta_minutes=round(eta, 1),
        breakdown={"base": base_fare, "km": km, "min": eta, "surge": surge},
    )
