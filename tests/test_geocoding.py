import pytest

from app.services.geocoding import LandmarkGeocoder


@pytest.mark.asyncio
async def test_resolve_maadi():
    g = LandmarkGeocoder()
    loc = await g.resolve("المعادي")
    assert loc is not None
    assert "معادي" in loc.name_ar


@pytest.mark.asyncio
async def test_resolve_alias():
    g = LandmarkGeocoder()
    loc = await g.resolve("سيتي ستارز")
    assert loc is not None
    assert "سيتي" in loc.name_ar or "ستارز" in loc.name_ar
