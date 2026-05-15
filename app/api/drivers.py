from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.matching import find_best_drivers

router = APIRouter(prefix="/api/drivers", tags=["drivers"])


@router.get("")
async def list_drivers_near(
    near: str = Query(..., description="lat,lng e.g. 30.04,31.23"),
    vehicle_type: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
):
    try:
        lat_s, lng_s = near.split(",", 1)
        lat, lng = float(lat_s.strip()), float(lng_s.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid near=lat,lng") from e
    matches = await find_best_drivers(session, lat, lng, vehicle_type, limit=limit)
    return {"drivers": [asdict(m) for m in matches]}
