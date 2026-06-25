"""Shared test setup.

`agent.py` constructs the pydantic-ai Agent at module-import time, and the
provider raises immediately if its API key isn't in os.environ. Setting dummy
keys here — BEFORE any test module imports weather_assistant — keeps test
collection from crashing. The dummy values are never sent anywhere: every test
either patches `weather_assistant.agent.get_weather` or uses `pytest-httpx`'s
fixture to intercept all outbound HTTP.
"""
import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-real")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
