"""LLM tool schemas + dispatcher wired to domain services."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Vehicle
from app.events.bus import EventBus
from app.services.geocoding import GeoProvider
from app.services.matching import find_best_drivers
from app.services.pricing import estimate_trip_price
from app.services.trips import (
    book_trip,
    cancel_trip,
    get_trip_status_dict,
    modify_trip,
    rate_driver,
)


class ResolveLocationArgs(BaseModel):
    query: str = Field(..., min_length=1)


class EstimatePriceArgs(BaseModel):
    pickup_query: str = Field(..., min_length=1)
    dropoff_query: str = Field(..., min_length=1)
    vehicle_type: str = Field(..., min_length=1)
    when_iso: str | None = None
    bad_weather: bool = False


class FindDriversArgs(BaseModel):
    pickup_query: str = Field(..., min_length=1)
    vehicle_type: str = Field(..., min_length=1)
    limit: int = Field(3, ge=1, le=10)


class BookTripArgs(BaseModel):
    user_id: str = Field(..., min_length=1)
    pickup_query: str = Field(..., min_length=1)
    dropoff_query: str = Field(..., min_length=1)
    vehicle_type: str = Field(..., min_length=1)
    preferred_driver_id: int | None = None
    when_iso: str | None = None
    bad_weather: bool = False


class GetTripStatusArgs(BaseModel):
    user_id: str = Field(..., min_length=1)
    trip_id: int = Field(..., ge=1)


class ModifyTripArgs(BaseModel):
    user_id: str = Field(..., min_length=1)
    trip_id: int = Field(..., ge=1)
    dropoff_query: str | None = None
    vehicle_type: str | None = None

    @model_validator(mode="after")
    def require_change(self) -> ModifyTripArgs:
        if not self.dropoff_query and not self.vehicle_type:
            raise ValueError("لازم تحدد وجهة جديدة أو نوع عربية للتعديل.")
        return self


class CancelTripArgs(BaseModel):
    user_id: str = Field(..., min_length=1)
    trip_id: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1)


class RateDriverArgs(BaseModel):
    user_id: str = Field(..., min_length=1)
    trip_id: int = Field(..., ge=1)
    stars: int = Field(..., ge=1, le=5)
    comment: str | None = None


def tool_definitions_openai() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "resolve_location",
                "description": "حوّل اسم مكان أو معلم في مصر لإحداثيات واسم عربي رسمي.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_vehicle_types",
                "description": "اعرض أنواع العربيات المتاحة (اقتصادي، مريح، عائلي، سكوتر) وأسعارها الأساسية.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "estimate_price",
                "description": "قدّر سعر الرحلة بالجنيه بين نقطتين مع نوع العربية (مع الأخذ في الاعتبار الزحمة والطلب).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pickup_query": {"type": "string"},
                        "dropoff_query": {"type": "string"},
                        "vehicle_type": {"type": "string"},
                        "when_iso": {"type": "string"},
                        "bad_weather": {"type": "boolean"},
                    },
                    "required": ["pickup_query", "dropoff_query", "vehicle_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_drivers",
                "description": "اقترح أفضل السواقين القريبين حسب التقييم والتوفر.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pickup_query": {"type": "string"},
                        "vehicle_type": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["pickup_query", "vehicle_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "book_trip",
                "description": "أكّد حجز رحلة بعد موافقة المستخدم على السعر والسواق.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "pickup_query": {"type": "string"},
                        "dropoff_query": {"type": "string"},
                        "vehicle_type": {"type": "string"},
                        "preferred_driver_id": {"type": "integer"},
                        "when_iso": {"type": "string"},
                        "bad_weather": {"type": "boolean"},
                    },
                    "required": ["user_id", "pickup_query", "dropoff_query", "vehicle_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_trip_status",
                "description": "جيب تفاصيل رحلة حالية أو سابقة (حالة، سعر، سواق، ETA).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "trip_id": {"type": "integer"},
                    },
                    "required": ["user_id", "trip_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "modify_trip",
                "description": "عدّل وجهة النزول أو نوع العربية قبل ما الرحلة تبدأ فعلياً.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "trip_id": {"type": "integer"},
                        "dropoff_query": {"type": "string"},
                        "vehicle_type": {"type": "string"},
                    },
                    "required": ["user_id", "trip_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_trip",
                "description": "إلغاء الرحلة مع سبب؛ قد يطبق رسوم إلغاء لو السواق في الطريق.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "trip_id": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["user_id", "trip_id", "reason"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rate_driver",
                "description": "قيّم السواق بعد انتهاء الرحلة (١–٥).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "trip_id": {"type": "integer"},
                        "stars": {"type": "integer"},
                        "comment": {"type": "string"},
                    },
                    "required": ["user_id", "trip_id", "stars"],
                },
            },
        },
    ]


@dataclass
class ToolContext:
    session: AsyncSession
    bus: EventBus
    geocoder: GeoProvider


class ToolDispatcher:
    def __init__(self, ctx: ToolContext) -> None:
        self.ctx = ctx

    async def dispatch(self, name: str, arguments_json: str) -> str:
        try:
            raw = json.loads(arguments_json or "{}")
        except json.JSONDecodeError:
            return json.dumps(
                {"ok": False, "error_ar": "البراميترات مش JSON صالح."},
                ensure_ascii=False,
            )
        try:
            return await self._dispatch(name, raw)
        except ValidationError as ve:
            return json.dumps(
                {"ok": False, "error_ar": "داتا ناقصة أو غلط: " + ve.errors()[0]["msg"]},
                ensure_ascii=False,
            )
        except ValueError as ve:
            return json.dumps({"ok": False, "error_ar": str(ve)}, ensure_ascii=False)
        except Exception as e:  # pragma: no cover - defensive
            return json.dumps(
                {"ok": False, "error_ar": "حصل خطأ: " + str(e)},
                ensure_ascii=False,
            )

    async def _dispatch(self, name: str, raw: dict[str, Any]) -> str:
        s = self.ctx.session
        bus = self.ctx.bus
        geo = self.ctx.geocoder

        if name == "resolve_location":
            a = ResolveLocationArgs.model_validate(raw)
            loc = await geo.resolve(a.query)
            if not loc:
                return json.dumps(
                    {"ok": False, "error_ar": "مش لاقي المكان ده في قاعدة المعالم. جرّب اسم أقرب أو أوضح."},
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "ok": True,
                    "name_ar": loc.name_ar,
                    "name_en": loc.name_en,
                    "lat": loc.lat,
                    "lng": loc.lng,
                    "area": loc.area,
                    "match_score": loc.score,
                },
                ensure_ascii=False,
            )

        if name == "list_vehicle_types":
            q = select(Vehicle).order_by(Vehicle.type_key)
            r = await s.execute(q)
            rows = r.scalars().all()
            return json.dumps(
                {
                    "ok": True,
                    "vehicles": [
                        {
                            "type_key": v.type_key,
                            "name_ar": v.name_ar,
                            "base_fare": v.base_fare,
                            "per_km": v.per_km,
                            "per_min": v.per_min,
                            "extra": v.extra,
                        }
                        for v in rows
                    ],
                },
                ensure_ascii=False,
            )

        if name == "estimate_price":
            a = EstimatePriceArgs.model_validate(raw)
            pu = await geo.resolve(a.pickup_query)
            du = await geo.resolve(a.dropoff_query)
            if not pu or not du:
                return json.dumps(
                    {"ok": False, "error_ar": "مش قادر أحدد نقطة الانطلاق أو الوصول."},
                    ensure_ascii=False,
                )
            v = (await s.execute(select(Vehicle).where(Vehicle.type_key == a.vehicle_type))).scalar_one_or_none()
            if not v:
                return json.dumps({"ok": False, "error_ar": "نوع العربية غلط."}, ensure_ascii=False)
            when = None
            if a.when_iso:
                try:
                    when = datetime.fromisoformat(a.when_iso.replace("Z", "+00:00"))
                except ValueError:
                    when = None
            est = await estimate_trip_price(
                s,
                pu.lat,
                pu.lng,
                du.lat,
                du.lng,
                v.base_fare,
                v.per_km,
                v.per_min,
                when=when,
                bad_weather=a.bad_weather,
            )
            return json.dumps(
                {
                    "ok": True,
                    "pickup": pu.name_ar,
                    "dropoff": du.name_ar,
                    "vehicle_type": a.vehicle_type,
                    "min_egp": est.min_egp,
                    "max_egp": est.max_egp,
                    "surge_factor": est.surge_factor,
                    "distance_km": est.distance_km,
                    "eta_minutes": est.eta_minutes,
                },
                ensure_ascii=False,
            )

        if name == "find_drivers":
            a = FindDriversArgs.model_validate(raw)
            pu = await geo.resolve(a.pickup_query)
            if not pu:
                return json.dumps(
                    {"ok": False, "error_ar": "مش لاقي نقطة الانطلاق."},
                    ensure_ascii=False,
                )
            matches = await find_best_drivers(s, pu.lat, pu.lng, a.vehicle_type, limit=a.limit)
            return json.dumps(
                {
                    "ok": True,
                    "pickup": pu.name_ar,
                    "drivers": [
                        {
                            "driver_id": m.driver_id,
                            "name_ar": m.name_ar,
                            "rating": m.rating,
                            "distance_km": m.distance_km,
                            "eta_pickup_minutes": m.eta_pickup_minutes,
                            "car": f"{m.car_make} {m.car_model}",
                            "plate": m.plate,
                            "score": m.score,
                        }
                        for m in matches
                    ],
                },
                ensure_ascii=False,
            )

        if name == "book_trip":
            a = BookTripArgs.model_validate(raw)
            pu = await geo.resolve(a.pickup_query)
            du = await geo.resolve(a.dropoff_query)
            if not pu or not du:
                return json.dumps(
                    {"ok": False, "error_ar": "مش قادر أحدد نقطة الانطلاق أو الوصول."},
                    ensure_ascii=False,
                )
            when = None
            if a.when_iso:
                try:
                    when = datetime.fromisoformat(a.when_iso.replace("Z", "+00:00"))
                except ValueError:
                    when = None
            trip = await book_trip(
                s,
                bus,
                a.user_id,
                pu,
                du,
                a.vehicle_type,
                preferred_driver_id=a.preferred_driver_id,
                when=when,
                bad_weather=a.bad_weather,
            )
            from app.services.trips import trip_to_dict

            return json.dumps({"ok": True, "trip": trip_to_dict(trip)}, ensure_ascii=False)

        if name == "get_trip_status":
            a = GetTripStatusArgs.model_validate(raw)
            d = await get_trip_status_dict(s, a.trip_id, a.user_id)
            return json.dumps({"ok": True, "trip": d}, ensure_ascii=False)

        if name == "modify_trip":
            a = ModifyTripArgs.model_validate(raw)
            drop = None
            if a.dropoff_query:
                drop = await geo.resolve(a.dropoff_query)
                if not drop:
                    return json.dumps(
                        {"ok": False, "error_ar": "مش لاقي الوجهة الجديدة."},
                        ensure_ascii=False,
                    )
            trip = await modify_trip(
                s,
                bus,
                a.trip_id,
                a.user_id,
                dropoff=drop,
                vehicle_type=a.vehicle_type,
            )
            from app.services.trips import trip_to_dict

            return json.dumps({"ok": True, "trip": trip_to_dict(trip)}, ensure_ascii=False)

        if name == "cancel_trip":
            a = CancelTripArgs.model_validate(raw)
            trip = await cancel_trip(s, bus, a.trip_id, a.user_id, a.reason)
            from app.services.trips import trip_to_dict

            return json.dumps({"ok": True, "trip": trip_to_dict(trip)}, ensure_ascii=False)

        if name == "rate_driver":
            a = RateDriverArgs.model_validate(raw)
            trip = await rate_driver(s, a.trip_id, a.user_id, a.stars, a.comment)
            from app.services.trips import trip_to_dict

            return json.dumps({"ok": True, "trip": trip_to_dict(trip)}, ensure_ascii=False)

        return json.dumps({"ok": False, "error_ar": f"أداة غير معروفة: {name}"}, ensure_ascii=False)
