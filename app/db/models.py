from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DriverStatus(str, enum.Enum):
    available = "available"
    busy = "busy"
    offline = "offline"


class TripStatus(str, enum.Enum):
    requested = "requested"
    assigned = "assigned"
    driver_en_route = "driver_en_route"
    arrived = "arrived"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trips: Mapped[list["Trip"]] = relationship(back_populates="user")
    messages: Mapped[list["Message"]] = relationship(back_populates="user")


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name_ar: Mapped[str] = mapped_column(String(64))
    base_fare: Mapped[float] = mapped_column(Float)
    per_km: Mapped[float] = mapped_column(Float)
    per_min: Mapped[float] = mapped_column(Float)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_ar: Mapped[str] = mapped_column(String(128))
    vehicle_type: Mapped[str] = mapped_column(String(32), index=True)
    car_make: Mapped[str] = mapped_column(String(64))
    car_model: Mapped[str] = mapped_column(String(64))
    plate: Mapped[str] = mapped_column(String(32))
    rating: Mapped[float] = mapped_column(Float, default=5.0)
    acceptance_rate: Mapped[float] = mapped_column(Float, default=0.95)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    status: Mapped[DriverStatus] = mapped_column(
        SQLEnum(DriverStatus, native_enum=False, length=32),
        default=DriverStatus.available,
    )

    trips: Mapped[list["Trip"]] = relationship(back_populates="driver")


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    driver_id: Mapped[int | None] = mapped_column(
        ForeignKey("drivers.id"), nullable=True, index=True
    )
    pickup_lat: Mapped[float] = mapped_column(Float)
    pickup_lng: Mapped[float] = mapped_column(Float)
    dropoff_lat: Mapped[float] = mapped_column(Float)
    dropoff_lng: Mapped[float] = mapped_column(Float)
    pickup_name_ar: Mapped[str] = mapped_column(String(256))
    dropoff_name_ar: Mapped[str] = mapped_column(String(256))
    vehicle_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[TripStatus] = mapped_column(
        SQLEnum(TripStatus, native_enum=False, length=32),
        default=TripStatus.requested,
    )
    estimated_price_min: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_price_max: Mapped[float] = mapped_column(Float, default=0.0)
    current_price: Mapped[float] = mapped_column(Float, default=0.0)
    surge_factor: Mapped[float] = mapped_column(Float, default=1.0)
    driver_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    driver_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    eta_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_rating_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="trips")
    driver: Mapped["Driver | None"] = relationship(back_populates="trips")
    events: Mapped[list["TripEvent"]] = relationship(
        back_populates="trip", order_by="TripEvent.created_at"
    )


class TripEvent(Base):
    __tablename__ = "trip_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="events")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text)
    tool_calls_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="messages")
