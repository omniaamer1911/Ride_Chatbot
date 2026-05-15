"""Idempotent seed: vehicles + drivers from JSON when tables are empty."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Driver, DriverStatus, Vehicle

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_json(name: str) -> list | dict:
    path = DATA_DIR / name
    with path.open(encoding="utf-8") as f:
        return json.load(f)


async def seed_if_empty(session: AsyncSession) -> None:
    vcount = await session.scalar(select(func.count()).select_from(Vehicle))
    if vcount == 0:
        vehicles = _load_json("vehicles.json")
        for v in vehicles:
            session.add(
                Vehicle(
                    type_key=v["type_key"],
                    name_ar=v["name_ar"],
                    base_fare=float(v["base_fare"]),
                    per_km=float(v["per_km"]),
                    per_min=float(v["per_min"]),
                    extra=v.get("extra"),
                )
            )
        await session.flush()

    dcount = await session.scalar(select(func.count()).select_from(Driver))
    if dcount == 0:
        drivers = _load_json("drivers_seed.json")
        for d in drivers:
            session.add(
                Driver(
                    name_ar=d["name_ar"],
                    vehicle_type=d["vehicle_type"],
                    car_make=d["car_make"],
                    car_model=d["car_model"],
                    plate=d["plate"],
                    rating=float(d["rating"]),
                    acceptance_rate=float(d["acceptance_rate"]),
                    lat=float(d["lat"]),
                    lng=float(d["lng"]),
                    status=DriverStatus(d.get("status", "available")),
                )
            )
        await session.flush()
