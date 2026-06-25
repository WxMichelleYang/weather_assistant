"""Open-Meteo client: geocode a city name, then fetch current weather."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT_S = 10.0
RETRY_DELAY_S = 0.5     # backoff before the single retry
MAX_ATTEMPTS = 2        # original + one retry


class WeatherError(Exception):
    """Raised when we can't return weather; the agent layer turns this into a tool-result string."""


@dataclass
class Weather:
    city: str
    country: str
    temperature_c: float
    wind_kmh: float
    weather_code: int


def _is_transient(e: httpx.HTTPError) -> bool:
    """Should this httpx error trigger a retry?

    Yes for timeouts, connect/network errors, and 5xx responses — these are
    routinely fixed by trying again. No for 4xx (won't help) or anything else.
    """
    if isinstance(e, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return True
    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500:
        return True
    return False


async def _get_with_retry(
    client: httpx.AsyncClient, url: str, params: dict
) -> httpx.Response:
    """GET with one retry on transient failures. Re-raises on permanent failure."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = await client.get(url, params=params, timeout=HTTP_TIMEOUT_S)
            r.raise_for_status()
            return r
        except httpx.HTTPError as e:
            if attempt >= MAX_ATTEMPTS or not _is_transient(e):
                raise
            logger.warning(
                "transient failure on %s (%s); retrying in %.1fs (attempt %d/%d)",
                url, e.__class__.__name__, RETRY_DELAY_S, attempt, MAX_ATTEMPTS,
            )
            await asyncio.sleep(RETRY_DELAY_S)
    raise RuntimeError("unreachable")  # for the type checker


async def _geocode(city: str, client: httpx.AsyncClient) -> dict:
    r = await _get_with_retry(client, GEOCODE_URL, {"name": city, "count": 1})
    results = r.json().get("results") or []
    if not results:
        raise WeatherError(f"No location found for {city!r}.")
    return results[0]


async def _forecast(latitude: float, longitude: float, client: httpx.AsyncClient) -> dict:
    r = await _get_with_retry(
        client,
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,wind_speed_10m,weather_code",
        },
    )
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
