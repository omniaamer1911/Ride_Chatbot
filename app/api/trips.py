from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.trips import get_trip_status_dict

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.get("/{trip_id}")
async def get_trip(
    trip_id: int,
    user_id: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await get_trip_status_dict(session, trip_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
