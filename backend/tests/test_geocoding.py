import httpx
import pytest

from kummo import geocoding
from kummo.config import Settings


@pytest.mark.asyncio
async def test_geocode_address_returns_coordinates(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "Kummo"
        assert request.url.params["q"] == "Oranienstraße 45, 10969 Berlin"
        assert request.url.params["format"] == "jsonv2"
        assert request.url.params["limit"] == "1"

        return httpx.Response(
            200,
            json=[{"lat": "52.5001", "lon": "13.4002"}],
        )

    transport = httpx.MockTransport(handler)

    original_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(geocoding.httpx, "AsyncClient", fake_client)

    settings = Settings.model_construct(
        geocoder_url="https://example.test/search",
        geocoder_user_agent="Kummo",
    )

    result = await geocoding.geocode_address(
        "Oranienstraße 45, 10969 Berlin",
        settings,
    )

    assert result == geocoding.Coordinates(
        latitude=52.5001,
        longitude=13.4002,
    )


@pytest.mark.asyncio
async def test_geocode_address_returns_none_when_nothing_matches(monkeypatch):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=[])
    )

    original_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(geocoding.httpx, "AsyncClient", fake_client)

    settings = Settings.model_construct(
        geocoder_url="https://example.test/search",
        geocoder_user_agent="Kummo",
    )

    result = await geocoding.geocode_address(
        "Nowhere",
        settings,
    )

    assert result is None
