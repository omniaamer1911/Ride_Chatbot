"""Haversine distance and simple ETA from straight-line km."""

from __future__ import annotations

import math


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def road_eta_minutes(
    straight_km: float,
    avg_kmh_city: float = 28.0,
    detour_factor: float = 1.35,
) -> float:
    """Rough ETA assuming urban average speed and detour vs straight line."""
    road_km = max(straight_km * detour_factor, 0.5)
    return (road_km / avg_kmh_city) * 60.0
