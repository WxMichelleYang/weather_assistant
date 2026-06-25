"""Pydantic AI agent: one tool, multi-turn history, streamed output."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from pydantic_ai import Agent, RunContext

from .config import MODEL
from .weather import WeatherError, get_weather

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a friendly weather assistant. When the user asks about weather, "
    "call weather_tool for each city mentioned. If the user mentions multiple "
    "cities, request all of them in a single turn so they run in parallel. "
    "After receiving the results, write one concise, conversational summary. "
    "Translate WMO weather codes into plain language (e.g. 0=clear sky, "
    "1-3=mainly clear to overcast, 45/48=fog, 51-67=drizzle/rain, "
    "71-77=snow, 80-82=rain showers, 95-99=thunderstorm). "
    "If a tool result begins with 'Error:', apologize briefly and explain what "
    "went wrong instead of guessing."
)


@dataclass
class Deps:
    http: httpx.AsyncClient


agent: Agent[Deps, str] = Agent(
    MODEL,
    deps_type=Deps,
    system_prompt=SYSTEM_PROMPT,
)


@agent.tool
async def weather_tool(ctx: RunContext[Deps], city: str) -> str:
    """Get current weather for a city.

    Args:
        city: The city name. Geocoded automatically (e.g. "London", "Tokyo", "San Francisco").
    """
    logger.info("weather_tool called for %r", city)
    try:
        w = await get_weather(city, ctx.deps.http)
    except WeatherError as e:
        logger.warning("weather_tool: %s", e)
        return f"Error: {e}"
    except httpx.HTTPError as e:
        logger.warning("weather_tool: HTTP error for %r: %s", city, e)
        return f"Error: weather service unavailable ({e.__class__.__name__})."
    country = f", {w.country}" if w.country else ""
    return (
        f"{w.city}{country}: {w.temperature_c}°C, "
        f"wind {w.wind_kmh} km/h, WMO weather code {w.weather_code}"
    )
