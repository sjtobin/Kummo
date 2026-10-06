from dataclasses import dataclass

import httpx

from .config import Settings


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


async def geocode_address(
    address: str,
    settings: Settings,
) -> Coordinates | None:
    """Resolve a postal address to coordinates.

    Returns None when the geocoder finds no matching location.
    Network/provider errors are allowed to propagate to the caller.
    """
    async with httpx.AsyncClient(
        timeout=5.0,
        headers={"User-Agent": settings.geocoder_user_agent},
    ) as client:
        response = await client.get(
            settings.geocoder_url,
            params={
                "q": address,
                "format": "jsonv2",
                "limit": 1,
            },
        )
        response.raise_for_status()

    matches = response.json()
    if not matches:
        return None

    match = matches[0]
    return Coordinates(
        latitude=float(match["lat"]),
        longitude=float(match["lon"]),
    )
