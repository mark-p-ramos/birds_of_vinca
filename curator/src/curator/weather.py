import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx


async def _geocode_zip(client: httpx.AsyncClient, zip_code: str) -> tuple[float, float]:
    """Convert a US zip code to lat/lon using Open-Meteo's geocoding API."""
    response = await client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": zip_code, "count": 1, "format": "json", "language": "en"},
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        raise ValueError(f"Could not geocode zip code: {zip_code}")
    return results[0]["latitude"], results[0]["longitude"]


def _parse_hourly_data(data: dict, hour: int) -> dict:
    """Extract weather for a specific hour from Open-Meteo hourly response."""
    hourly = data["hourly"]
    times = hourly["time"]

    # Find the index matching the target hour
    idx = next(
        i for i, t in enumerate(times) if datetime.strptime(t, "%Y-%m-%dT%H:%M").hour == hour
    )

    return {
        "temperature_f": hourly["temperature_2m"][idx],
        "was_cloudy": hourly["cloud_cover"][idx] > 50,
        "was_precipitating": hourly["precipitation"][idx] > 0,
    }


_HOURLY_PARAMS = "temperature_2m,cloud_cover,precipitation"
_UNIT_PARAMS: dict[str, str] = {"temperature_unit": "fahrenheit", "precipitation_unit": "inch"}


async def _get_historical_weather(
    client: httpx.AsyncClient, lat: float, lon: float, dt: datetime
) -> dict:
    date_str = dt.strftime("%Y-%m-%d")
    params: dict[str, str] = {
        "latitude": str(lat),
        "longitude": str(lon),
        "start_date": date_str,
        "end_date": date_str,
        "hourly": _HOURLY_PARAMS,
        **_UNIT_PARAMS,
    }
    response = await client.get("https://archive-api.open-meteo.com/v1/archive", params=params)
    response.raise_for_status()
    return _parse_hourly_data(response.json(), dt.hour)


async def _get_today_weather(
    client: httpx.AsyncClient, lat: float, lon: float, dt: datetime
) -> dict:
    params: dict[str, str] = {
        "latitude": str(lat),
        "longitude": str(lon),
        "forecast_days": "1",
        "hourly": _HOURLY_PARAMS,
        **_UNIT_PARAMS,
    }
    response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
    response.raise_for_status()
    return _parse_hourly_data(response.json(), dt.hour)


async def get_weather(location_zip: str, dt: datetime) -> dict:
    """
    Retrieve weather from Open-Meteo for a specific datetime.

    Uses the forecast endpoint for today's date and the archive endpoint
    for past dates. Geocodes zip codes to lat/lon automatically.

    Args:
        location (str): US ZIP code or "lat,lon".
        dt (datetime): The datetime you want weather for.

    Returns:
        dict with:
            - temperature_f (float)
            - was_cloudy (bool)
            - was_precipitating (bool)
    """
    async with httpx.AsyncClient() as client:
        lat, lon = await _geocode_zip(client, location_zip)
        if dt.date() == date.today():
            return await _get_today_weather(client, lat, lon, dt)
        return await _get_historical_weather(client, lat, lon, dt)


if __name__ == "__main__":
    dt = datetime.now(timezone.utc) - timedelta(days=3)
    weather = asyncio.run(get_weather("80027", dt))
    print(weather)
