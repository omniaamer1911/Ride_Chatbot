"""Background task: advance active trips and broadcast updates."""

from __future__ import annotations

import asyncio
import math

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import Driver, DriverStatus, Trip, TripStatus, User
from app.db.session import async_session_factory
from app.events.bus import EventBus
from app.services.geo_utils import haversine_km, road_eta_minutes
from app.services.trips import log_event


def _move_toward(
    lat: float, lng: float, tlat: float, tlng: float, fraction: float
) -> tuple[float, float]:
    return (
        lat + fraction * (tlat - lat),
        lng + fraction * (tlng - lng),
    )


async def _advance_one(session, trip: Trip, bus: EventBus) -> None:
    settings = get_settings()
    alpha = 0.22
    user_ext = trip.user.external_id
    driver = trip.driver
    if not driver:
        return

    if trip.status == TripStatus.driver_en_route:
        dlat, dlng = trip.driver_lat or driver.lat, trip.driver_lng or driver.lng
        dist = haversine_km(dlat, dlng, trip.pickup_lat, trip.pickup_lng)
        if dist < 0.04:
            trip.status = TripStatus.arrived
            trip.driver_lat = trip.pickup_lat
            trip.driver_lng = trip.pickup_lng
            trip.eta_minutes = 0.0
            await log_event(session, trip.id, "arrived", {})
            await bus.publish(
                user_ext,
                {
                    "type": "trip_update",
                    "trip_id": trip.id,
                    "status": trip.status.value,
                    "message_ar": "السواق وصل لنقطة الالتقاط.",
                },
            )
        else:
            nlat, nlng = _move_toward(
                dlat, dlng, trip.pickup_lat, trip.pickup_lng, alpha
            )
            trip.driver_lat, trip.driver_lng = nlat, nlng
            trip.eta_minutes = round(road_eta_minutes(dist, avg_kmh_city=30.0), 1)
            trip.current_price = min(
                trip.estimated_price_max,
                trip.current_price
                + (trip.estimated_price_max - trip.estimated_price_min) * 0.02,
            )
            await bus.publish(
                user_ext,
                {
                    "type": "trip_update",
                    "trip_id": trip.id,
                    "status": trip.status.value,
                    "driver_lat": nlat,
                    "driver_lng": nlng,
                    "eta_minutes": trip.eta_minutes,
                    "current_price_egp": round(trip.current_price, 2),
                },
            )

    elif trip.status == TripStatus.arrived:
        trip.status = TripStatus.in_progress
        await log_event(session, trip.id, "started", {})
        await bus.publish(
            user_ext,
            {
                "type": "trip_update",
                "trip_id": trip.id,
                "status": trip.status.value,
                "message_ar": "الرحلة بدأت، بالسلامة.",
            },
        )

    elif trip.status == TripStatus.in_progress:
        dlat = trip.driver_lat or trip.pickup_lat
        dlng = trip.driver_lng or trip.pickup_lng
        dist = haversine_km(dlat, dlng, trip.dropoff_lat, trip.dropoff_lng)
        if dist < 0.04:
            trip.status = TripStatus.completed
            trip.driver_lat = trip.dropoff_lat
            trip.driver_lng = trip.dropoff_lng
            trip.current_price = trip.estimated_price_max * (
                0.92 + 0.06 * math.sin(trip.id)
            )  # slight variance
            trip.current_price = round(min(trip.estimated_price_max * 1.05, trip.current_price), 2)
            trip.eta_minutes = 0.0
            driver.status = DriverStatus.available
            await log_event(session, trip.id, "completed", {"price": trip.current_price})
            await bus.publish(
                user_ext,
                {
                    "type": "trip_update",
                    "trip_id": trip.id,
                    "status": trip.status.value,
                    "current_price_egp": trip.current_price,
                    "message_ar": "وصلنا. متنساش تقيّم السواق لو حابب.",
                },
            )
        else:
            nlat, nlng = _move_toward(
                dlat, dlng, trip.dropoff_lat, trip.dropoff_lng, alpha
            )
            trip.driver_lat, trip.driver_lng = nlat, nlng
            trip.eta_minutes = round(road_eta_minutes(dist, avg_kmh_city=30.0), 1)
            total_km = haversine_km(
                trip.pickup_lat, trip.pickup_lng, trip.dropoff_lat, trip.dropoff_lng
            )
            done_km = haversine_km(
                trip.pickup_lat, trip.pickup_lng, nlat, nlng
            )
            prog = min(1.0, done_km / max(total_km, 0.01))
            trip.current_price = round(
                trip.estimated_price_min
                + prog * (trip.estimated_price_max - trip.estimated_price_min),
                2,
            )
            await bus.publish(
                user_ext,
                {
                    "type": "trip_update",
                    "trip_id": trip.id,
                    "status": trip.status.value,
                    "driver_lat": nlat,
                    "driver_lng": nlng,
                    "eta_minutes": trip.eta_minutes,
                    "current_price_egp": trip.current_price,
                },
            )

    _ = settings  # reserved for future tuning


async def simulator_loop(stop: asyncio.Event, bus: EventBus) -> None:
    settings = get_settings()
    factory = async_session_factory()
    while not stop.is_set():
        async with factory() as session:
            try:
                active = (
                    TripStatus.driver_en_route,
                    TripStatus.arrived,
                    TripStatus.in_progress,
                )
                q = (
                    select(Trip)
                    .options(
                        selectinload(Trip.user),
                        selectinload(Trip.driver),
                    )
                    .where(Trip.status.in_(active))
                )
                res = await session.execute(q)
                trips = list(res.scalars().all())
                for trip in trips:
                    await _advance_one(session, trip, bus)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.trip_simulator_interval_sec
            )
        except asyncio.TimeoutError:
            pass
