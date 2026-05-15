"""Landmark geocoding with Arabic normalization and fuzzy match."""

from __future__ import annotations

import json
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def normalize_arabic(text: str) -> str:
    """Loose normalization for matching user queries."""
    t = unicodedata.normalize("NFKC", text)
    t = t.strip().lower()
    # Remove tatweel and diacritics
    t = re.sub(r"[\u0640\u0617-\u061A\u064B-\u0652]", "", t)
    # Normalize alef variants
    t = re.sub(r"[إأآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه")
    t = re.sub(r"\s+", " ", t)
    return t


@dataclass
class ResolvedLocation:
    name_ar: str
    name_en: str
    lat: float
    lng: float
    area: str
    score: float


class GeoProvider(ABC):
    """Pluggable geocoder (landmarks now; Google Places later)."""

    @abstractmethod
    async def resolve(self, query: str) -> ResolvedLocation | None:
        pass


class LandmarkGeocoder(GeoProvider):
    def __init__(self, landmarks_path: Path | None = None) -> None:
        path = landmarks_path or (DATA_DIR / "landmarks.json")
        with path.open(encoding="utf-8") as f:
            raw: list[dict[str, Any]] = json.load(f)
        self._items: list[dict[str, Any]] = raw
        self._choices: list[str] = []
        self._index: dict[str, dict[str, Any]] = {}
        for item in raw:
            key = normalize_arabic(item["name_ar"])
            self._choices.append(key)
            self._index[key] = item
            for alias in item.get("aliases", []) or []:
                ak = normalize_arabic(alias)
                self._choices.append(ak)
                self._index[ak] = item
            en = item.get("name_en") or ""
            if en:
                ek = normalize_arabic(en)
                self._choices.append(ek)
                self._index[ek] = item

    async def resolve(self, query: str) -> ResolvedLocation | None:
        qn = normalize_arabic(query)
        if not qn:
            return None
        # Exact-ish
        if qn in self._index:
            it = self._index[qn]
            return self._to_resolved(it, 100.0)
        match = process.extractOne(
            qn,
            self._choices,
            scorer=fuzz.WRatio,
        )
        if not match or match[1] < 70:
            return None
        it = self._index[match[0]]
        return self._to_resolved(it, float(match[1]))

    def _to_resolved(self, item: dict[str, Any], score: float) -> ResolvedLocation:
        return ResolvedLocation(
            name_ar=item["name_ar"],
            name_en=item.get("name_en", ""),
            lat=float(item["lat"]),
            lng=float(item["lng"]),
            area=item.get("area", ""),
            score=score,
        )
