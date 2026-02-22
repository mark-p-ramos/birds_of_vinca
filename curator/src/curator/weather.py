from datetime import datetime

import httpx


async def get_historical_weather(api_key: str, location: str, dt: datetime) -> dict:
    """
    Retrieve historical weather from WeatherAPI.com for a specific datetime.

    Args:
        api_key (str): Your WeatherAPI.com API key.
        location (str): City name, ZIP, or "lat,lon".
        dt (datetime): The datetime you want weather for (local time of location).

    Returns:
        dict with:
            - temperature_f (float)
            - was_cloudy (bool)
            - was_raining (bool)
    """

    base_url = "https://api.weatherapi.com/v1/history.json"
    date_str = dt.strftime("%Y-%m-%d")
    hour = dt.hour

    params = {"key": api_key, "q": location, "dt": date_str}

    async with httpx.AsyncClient() as client:
        response = await client.get(base_url, params=params)
    response.raise_for_status()

    data = response.json()

    # WeatherAPI returns hourly data inside forecast -> forecastday -> hour[]
    hours = data["forecast"]["forecastday"][0]["hour"]

    # Find the matching hour
    hour_data = next(
        h for h in hours if datetime.strptime(h["time"], "%Y-%m-%d %H:%M").hour == hour
    )

    temperature_f = hour_data["temp_f"]

    # Cloud logic
    # Consider cloudy if cloud cover > 50%
    was_cloudy = hour_data["cloud"] > 50

    # Rain logic
    # Consider raining if precipitation > 0 inches
    was_raining = hour_data["precip_in"] > 0

    return {
        "temperature_f": temperature_f,
        "was_cloudy": was_cloudy,
        "was_precipitating": was_raining,
    }
