"""Tests for weather.py — Open-Meteo geocode + forecast client.

Uses pytest-httpx's `httpx_mock` fixture to intercept all outbound httpx
requests. We test both the response-parsing (Weather fields) and the
geocode→forecast request contract (correct URLs + query params).
"""
from __future__ import annotations

import httpx
import pytest

from weather_assistant.weather import (
    FORECAST_URL,
    GEOCODE_URL,
    Weather,
    WeatherError,
    get_weather,
)


async def test_get_weather_happy_path(httpx_mock):
    httpx_mock.add_response(
        json={
            "results": [
                {
                    "name": "London",
                    "country": "United Kingdom",
                    "latitude": 51.5074,
                    "longitude": -0.1278,
                }
            ]
        },
    )
    httpx_mock.add_response(
        json={
            "current": {
                "temperature_2m": 18.3,
                "wind_speed_10m": 10.4,
                "weather_code": 3,
            }
        },
    )

    async with httpx.AsyncClient() as client:
        w = await get_weather("London", client)

    assert w == Weather(
        city="London",
        country="United Kingdom",
        temperature_c=18.3,
        wind_kmh=10.4,
        weather_code=3,
    )

    # Verify the two-step contract: geocode first, then forecast with the
    # coordinates from the geocode response.
    requests = httpx_mock.get_requests()
    assert len(requests) == 2

    geo, forecast = requests
    assert str(geo.url).startswith(GEOCODE_URL)
    assert geo.url.params["name"] == "London"
    assert geo.url.params["count"] == "1"

    assert str(forecast.url).startswith(FORECAST_URL)
    assert forecast.url.params["latitude"] == "51.5074"
    assert forecast.url.params["longitude"] == "-0.1278"
    assert "temperature_2m" in forecast.url.params["current"]


async def test_get_weather_unknown_city_raises_weather_error(httpx_mock):
    # Open-Meteo returns 200 with an empty/missing `results` for unknown places.
    httpx_mock.add_response(json={})

    async with httpx.AsyncClient() as client:
        with pytest.raises(WeatherError, match="Atlantis"):
            await get_weather("Atlantis", client)


async def test_get_weather_forecast_4xx_propagates_without_retry(httpx_mock):
    # Geocode succeeds, forecast returns 404 (non-transient → no retry).
    # Complements the geocode 4xx and 5xx-exhausted cases below.
    httpx_mock.add_response(
        json={"results": [{"name": "London", "country": "UK", "latitude": 51.5, "longitude": -0.1}]},
    )
    httpx_mock.add_response(status_code=404)

    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await get_weather("London", client)

    # Two requests total: successful geocode + the one failed forecast (no retry).
    assert len(httpx_mock.get_requests()) == 2


async def test_get_weather_missing_country_field(httpx_mock):
    # Some Open-Meteo geocoding results omit `country` (e.g. ocean coordinates).
    # We default to an empty string so the dataclass doesn't blow up.
    httpx_mock.add_response(
        json={"results": [{"name": "Somewhere", "latitude": 0.0, "longitude": 0.0}]},
    )
    httpx_mock.add_response(
        json={"current": {"temperature_2m": 20.0, "wind_speed_10m": 5.0, "weather_code": 0}},
    )

    async with httpx.AsyncClient() as client:
        w = await get_weather("Somewhere", client)

    assert w.country == ""


# --- Retry behavior ---------------------------------------------------------

async def test_get_weather_retries_on_5xx_and_succeeds(httpx_mock):
    # First geocode attempt → 503, retry succeeds, then forecast succeeds.
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(
        json={"results": [{"name": "London", "country": "UK", "latitude": 51.5, "longitude": -0.1}]},
    )
    httpx_mock.add_response(
        json={"current": {"temperature_2m": 18.0, "wind_speed_10m": 10.0, "weather_code": 3}},
    )

    async with httpx.AsyncClient() as client:
        w = await get_weather("London", client)

    assert w.city == "London"
    # Three requests in total: failed geocode + retried geocode + forecast.
    assert len(httpx_mock.get_requests()) == 3


async def test_get_weather_does_not_retry_on_4xx(httpx_mock):
    # 404 isn't transient — must not retry. Single request, raises immediately.
    httpx_mock.add_response(status_code=404)

    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await get_weather("London", client)

    assert len(httpx_mock.get_requests()) == 1


async def test_get_weather_retry_exhausted_raises(httpx_mock):
    # Both attempts return 500 → raise the HTTPStatusError from the second.
    httpx_mock.add_response(status_code=500)
    httpx_mock.add_response(status_code=500)

    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await get_weather("London", client)

    # Two attempts on geocode; no forecast attempted.
    assert len(httpx_mock.get_requests()) == 2
