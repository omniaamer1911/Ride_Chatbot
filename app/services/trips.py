"""Trip lifecycle: book, modify, cancel, status."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Driver, DriverStatus, Trip, TripEvent, TripStatus, User, Vehicle
from app.services.geocoding import ResolvedLocation
from app.services.matching import find_best_drivers
from app.services.pricing import estimate_trip_price


async def get_or_create_user(session: AsyncSession, external_id: str) -> User:
    q = select(User).where(User.external_id == external_id)
    r = await session.execute(q)
    u = r.scalar_one_or_none()
    if u:
        return u
    u = User(external_id=external_id)
    session.add(u)
    await session.flush()
    return u


async def get_vehicle(session: AsyncSession, type_key: str) -> Vehicle | None:
    q = select(Vehicle).where(Vehicle.type_key == type_key)
    r = await session.execute(q)
    return r.scalar_one_or_none()


async def log_event(
    session: AsyncSession, trip_id: int, event_type: str, payload: dict[str, Any] | None = None
) -> None:
    session.add(TripEvent(trip_id=trip_id, event_type=event_type, payload=payload or {}))


async def book_trip(
    session: AsyncSession,
    user_external_id: str,
    pickup: ResolvedLocation,
    dropoff: ResolvedLocation,
    vehicle_type: str,
    preferred_driver_id: int | None = None,
    when: datetime | None = None,
    bad_weather: bool = False,
) -> Trip:
    user = await get_or_create_user(session, user_external_id)
    vehicle = await get_vehicle(session, vehicle_type)
    if not vehicle:
        raise ValueError("نوع العربية مش متاح.")

    price = await estimate_trip_price(
        session,
        pickup.lat,
        pickup.lng,
        dropoff.lat,
        dropoff.lng,
        vehicle.base_fare,
        vehicle.per_km,
        vehicle.per_min,
        when=when,
        bad_weather=bad_weather,
    )

    if preferred_driver_id:
        dq = select(Driver).where(Driver.id == preferred_driver_id)
        dr = await session.execute(dq)
        driver = dr.scalar_one_or_none()
        if (
            not driver
            or driver.status != DriverStatus.available
            or driver.vehicle_type != vehicle_type
        ):
            raise ValueError("السواق المختار مش متاح دلوقتي.")
        chosen = driver
    else:
        matches = await find_best_drivers(
            session, pickup.lat, pickup.lng, vehicle_type, limit=1
        )
        if not matches:
            raise ValueError("مفيش سواقين فاضيين قريب منك في الوقت الحالي.")
        dq = select(Driver).where(Driver.id == matches[0].driver_id)
        dr = await session.execute(dq)
        chosen = dr.scalar_one()

    trip = Trip(
        user_id=user.id,
        driver_id=chosen.id,
        pickup_lat=pickup.lat,
        pickup_lng=pickup.lng,
        dropoff_lat=dropoff.lat,
        dropoff_lng=dropoff.lng,
        pickup_name_ar=pickup.name_ar,
        dropoff_name_ar=dropoff.name_ar,
        vehicle_type=vehicle_type,
        status=TripStatus.driver_en_route,
        estimated_price_min=price.min_egp,
        estimated_price_max=price.max_egp,
        current_price=price.min_egp,
        surge_factor=price.surge_factor,
        driver_lat=chosen.lat,
        driver_lng=chosen.lng,
        eta_minutes=price.eta_minutes,
    )
    chosen.status = DriverStatus.busy
    session.add(trip)
    await session.flush()
    await log_event(
        session,
        trip.id,
        "booked",
        {
            "pickup": pickup.name_ar,
            "dropoff": dropoff.name_ar,
            "vehicle_type": vehicle_type,
            "driver": chosen.name_ar,
        },
    )
    # Wire driver in-memory so trip_to_dict does not trigger async lazy-load IO.
    trip.driver = chosen
    return trip


async def reload_trip_with_driver(session: AsyncSession, trip: Trip) -> Trip:
    """Eager-load driver for API/tool responses (avoids MissingGreenlet in async)."""
    q = (
        select(Trip)
        .where(Trip.id == trip.id)
        .options(selectinload(Trip.driver))
    )
    return (await session.execute(q)).scalar_one()


def _modifiable(status: TripStatus) -> bool:
    return status in (
        TripStatus.requested,
        TripStatus.assigned,
        TripStatus.driver_en_route,
    )


async def modify_trip(
    session: AsyncSession,
    trip_id: int,
    user_external_id: str,
    dropoff: ResolvedLocation | None = None,
    vehicle_type: str | None = None,
) -> Trip:
    trip = await get_trip_for_user(session, trip_id, user_external_id)
    if not _modifiable(trip.status):
        raise ValueError("مينفعش تعديل الرحلة في المرحلة دي.")

    if dropoff:
        trip.dropoff_lat = dropoff.lat
        trip.dropoff_lng = dropoff.lng
        trip.dropoff_name_ar = dropoff.name_ar

    if vehicle_type and vehicle_type != trip.vehicle_type:
        vehicle = await get_vehicle(session, vehicle_type)
        if not vehicle:
            raise ValueError("نوع العربية مش متاح.")
        matches = await find_best_drivers(
            session, trip.pickup_lat, trip.pickup_lng, vehicle_type, limit=1
        )
        if not matches:
            raise ValueError("مفيش سواقين للنوع ده قريب من نقطة الانطلاق.")
        old_driver_id = trip.driver_id
        dq = select(Driver).where(Driver.id == matches[0].driver_id)
        new_driver = (await session.execute(dq)).scalar_one()
        if old_driver_id:
            od = await session.get(Driver, old_driver_id)
            if od:
                od.status = DriverStatus.available
        trip.driver_id = new_driver.id
        new_driver.status = DriverStatus.busy
        trip.vehicle_type = vehicle_type
        trip.driver_lat = new_driver.lat
        trip.driver_lng = new_driver.lng

    v = await get_vehicle(session, trip.vehicle_type)
    if not v:
        raise ValueError("نوع العربية مش متاح.")
    price = await estimate_trip_price(
        session,
        trip.pickup_lat,
        trip.pickup_lng,
        trip.dropoff_lat,
        trip.dropoff_lng,
        v.base_fare,
        v.per_km,
        v.per_min,
    )
    trip.estimated_price_min = price.min_egp
    trip.estimated_price_max = price.max_egp
    trip.surge_factor = price.surge_factor
    trip.eta_minutes = price.eta_minutes

    await log_event(
        session,
        trip.id,
        "modified",
        {"dropoff": dropoff.name_ar if dropoff else None, "vehicle_type": vehicle_type},
    )
    return trip


async def cancel_trip(
    session: AsyncSession,
    trip_id: int,
    user_external_id: str,
    reason: str,
) -> Trip:
    trip = await get_trip_for_user(session, trip_id, user_external_id)
    if trip.status in (TripStatus.completed, TripStatus.cancelled):
        raise ValueError("الرحلة خلصت أو اتلغت قبل كده.")

    fee = 0.0
    if trip.status in (TripStatus.driver_en_route, TripStatus.arrived):
        fee = min(25.0, trip.estimated_price_min * 0.15)

    trip.status = TripStatus.cancelled
    trip.cancel_reason = reason
    if fee > 0:
        trip.current_price = fee
    if trip.driver_id:
        d = await session.get(Driver, trip.driver_id)
        if d:
            d.status = DriverStatus.available
    await log_event(session, trip.id, "cancelled", {"reason": reason, "fee": fee})
    return trip


async def rate_driver(
    session: AsyncSession,
    trip_id: int,
    user_external_id: str,
    stars: int,
    comment: str | None,
) -> Trip:
    trip = await get_trip_for_user(session, trip_id, user_external_id)
    if trip.status != TripStatus.completed:
        raise ValueError("التقييم متاح بعد ما الرحلة تخلص بس.")
    if not (1 <= stars <= 5):
        raise ValueError("التقييم لازم يكون من ١ لـ ٥.")
    trip.user_rating = stars
    trip.user_rating_comment = comment
    await log_event(session, trip.id, "rated", {"stars": stars})
    return trip


async def get_trip_for_user(
    session: AsyncSession, trip_id: int, user_external_id: str
) -> Trip:
    u = await get_or_create_user(session, user_external_id)
    q = (
        select(Trip)
        .options(selectinload(Trip.driver), selectinload(Trip.user))
        .where(Trip.id == trip_id, Trip.user_id == u.id)
    )
    r = await session.execute(q)
    trip = r.scalar_one_or_none()
    if not trip:
        raise ValueError("مش لاقي رحلة بالرقم ده لحسابك.")
    return trip


def _loaded_driver(trip: Trip) -> Driver | None:
    """Return driver only if already loaded on the instance (no lazy IO)."""
    if "driver" in sa_inspect(trip).unloaded:
        return None
    return trip.driver


def trip_to_dict(trip: Trip) -> dict[str, Any]:
    driver = _loaded_driver(trip)
    out: dict[str, Any] = {
        "trip_id": trip.id,
        "status": trip.status.value,
        "pickup_name_ar": trip.pickup_name_ar,
        "dropoff_name_ar": trip.dropoff_name_ar,
        "vehicle_type": trip.vehicle_type,
        "estimated_price_min": trip.estimated_price_min,
        "estimated_price_max": trip.estimated_price_max,
        "current_price_egp": trip.current_price,
        "surge_factor": trip.surge_factor,
        "eta_minutes": trip.eta_minutes,
        "driver_lat": trip.driver_lat,
        "driver_lng": trip.driver_lng,
    }
    if driver:
        out["driver"] = {
            "name_ar": driver.name_ar,
            "car": f"{driver.car_make} {driver.car_model}",
            "plate": driver.plate,
            "rating": driver.rating,
        }
    return out


async def get_trip_status_dict(
    session: AsyncSession, trip_id: int, user_external_id: str
) -> dict[str, Any]:
    trip = await get_trip_for_user(session, trip_id, user_external_id)
    return trip_to_dict(trip)
