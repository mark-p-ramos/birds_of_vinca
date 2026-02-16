import requests

_SUPERIOR_CO_LAT = 39.921636
_SUPERIOR_CO_LONG = -105.149215

_HEADERS = {
    "User-Agent": "birds-of-vinca (mark.p.ramos@gmail.com)",
    "Accept": "application/geo+json",
}


def get_current_weather(lat: float = _SUPERIOR_CO_LAT, lon: float = _SUPERIOR_CO_LONG) -> dict:
    # 1. Get forecast metadata (includes nearby stations)
    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    points_resp = requests.get(points_url, headers=_HEADERS)
    points_resp.raise_for_status()
    points_data = points_resp.json()

    # 2. Get nearest observation station
    stations_url = points_data["properties"]["observationStations"]
    stations_resp = requests.get(stations_url, headers=_HEADERS)
    stations_resp.raise_for_status()
    station_id = stations_resp.json()["features"][0]["properties"]["stationIdentifier"]

    # 3. Get latest observation
    obs_url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
    obs_resp = requests.get(obs_url, headers=_HEADERS)
    obs_resp.raise_for_status()
    obs = obs_resp.json()["properties"]

    # Temperature (C → F)
    temp_c = obs["temperature"]["value"]
    temperature_f = None
    if temp_c is not None:
        temperature_f = round(temp_c * 9 / 5 + 32, 1)

    # Cloud / sky condition
    sky = obs.get("textDescription", "").lower()
    is_cloudy = "cloud" in sky or "overcast" in sky

    # Precipitation
    is_precipitating = obs["precipitationLastHour"]["value"] not in (None, 0)

    return {
        "temperature_f": temperature_f,
        "sky_description": obs["textDescription"],
        "is_cloudy": is_cloudy,
        "is_precipitating": is_precipitating,
    }
