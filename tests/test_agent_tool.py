"""Tests for the @agent.tool wrapper around get_weather.

The wrapper's job is to convert exceptions into model-readable strings so the
LLM can apologize gracefully rather than the REPL crashing. We test the
three branches: success, WeatherError, and httpx.HTTPError.

We patch `weather_assistant.agent.get_weather` (the name as imported into
agent.py) rather than mocking httpx, so we're testing the wrapper's
exception-handling logic in isolation. weather.py is exercised separately
in test_weather.py.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from weather_assistant.agent import weather_tool
from weather_assistant.weather import Weather, WeatherError


def _fake_ctx():
    """Minimal duck-typed RunContext — weather_tool only reads ctx.deps.http."""
    return SimpleNamespace(deps=SimpleNamespace(http=AsyncMock()))


async def test_weather_tool_happy_path_formats_string_for_model():
    fake = Weather(
        city="London",
        country="United Kingdom",
        temperature_c=18.3,
        wind_kmh=10.4,
        weather_code=3,
    )
    with patch("weather_assistant.agent.get_weather", AsyncMock(return_value=fake)):
        result = await weather_tool(_fake_ctx(), "London")

    # The string is what the LLM sees as the tool result; verify the key facts
    # are in it without pinning the exact format (which we may tweak later).
    assert "London" in result
    assert "United Kingdom" in result
    assert "18.3" in result
    assert "10.4" in result
    assert "3" in result  # weather code
    assert not result.startswith("Error:")


async def test_weather_tool_happy_path_omits_country_when_blank():
    fake = Weather(city="Somewhere", country="", temperature_c=20.0, wind_kmh=5.0, weather_code=0)
    with patch("weather_assistant.agent.get_weather", AsyncMock(return_value=fake)):
        result = await weather_tool(_fake_ctx(), "Somewhere")

    # No ", " injected for a blank country.
    assert "Somewhere:" in result
    assert "Somewhere, :" not in result


async def test_weather_tool_translates_weather_error_to_tool_result():
    err = WeatherError("No location found for 'Atlantis'.")
    with patch("weather_assistant.agent.get_weather", AsyncMock(side_effect=err)):
        result = await weather_tool(_fake_ctx(), "Atlantis")

    assert result.startswith("Error:")
    assert "Atlantis" in result


async def test_weather_tool_translates_http_error_to_tool_result():
    err = httpx.ConnectTimeout("timed out connecting to api.open-meteo.com")
    with patch("weather_assistant.agent.get_weather", AsyncMock(side_effect=err)):
        result = await weather_tool(_fake_ctx(), "London")

    assert result.startswith("Error: weather service unavailable")
    assert "ConnectTimeout" in result
