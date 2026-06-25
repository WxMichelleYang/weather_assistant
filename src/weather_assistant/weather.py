"""Open-Meteo client: geocode a city name, then fetch current weather."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT_S = 10.0


class WeatherError(Exception):
    """Raised when we can't return weather; the agent layer turns this into a tool-result string."""


@dataclass
class Weather:
    city: str
    country: str
    temperature_c: float
    wind_kmh: float
    weather_code: int


async def _geocode(city: str, client: httpx.AsyncClient) -> dict:
    r = await client.get(
        GEOCODE_URL,
        params={"name": city, "count": 1},
        timeout=HTTP_TIMEOUT_S,
    )
    r.raise_for_status()
    results = r.json().get("results") or []
    if not results:
        raise WeatherError(f"No location found for {city!r}.")
    return results[0]


async def _forecast(latitude: float, longitude: float, client: httpx.AsyncClient) -> dict:
    r = await client.get(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,wind_speed_10m,weather_code",
        },
        timeout=HTTP_TIMEOUT_S,
    )
    r.raise_for_status()
    return r.json()["current"]


async def get_weather(city: str, client: httpx.AsyncClient) -> Weather:
    """Resolve a city name to coordinates and return current weather."""
    logger.debug("geocoding %r", city)
    place = await _geocode(city, client)
    logger.debug(
        "geocoded %r → %s, %s (lat=%s lon=%s)",
        city, place["name"], place.get("country", ""), place["latitude"], place["longitude"],
    )
    current = await _forecast(place["latitude"], place["longitude"], client)
    logger.debug("forecast for %r: %s°C, wind %s km/h, code %s",
                 city, current["temperature_2m"], current["wind_speed_10m"], current["weather_code"])
    return Weather(
        city=place["name"],
        country=place.get("country", ""),
        temperature_c=current["temperature_2m"],
        wind_kmh=current["wind_speed_10m"],
        weather_code=current["weather_code"],
    )
