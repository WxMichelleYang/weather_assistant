"""Config read from the environment at import time.

Kept as a separate module so `__main__.py` can read `MODEL` BEFORE importing
`.agent` — agent.py builds the pydantic-ai Agent at module-load and would fail
without the right API key in os.environ.
"""
from __future__ import annotations

import os

DEFAULT_MODEL = "google:gemini-2.5-flash"
MODEL = os.getenv("MODEL", DEFAULT_MODEL)

# Provider prefix → env var that the corresponding pydantic-ai provider expects.
# Add a row when adopting a new provider; if a prefix isn't listed, the fast-fail
# is skipped and pydantic-ai's own error message takes over.
_PROVIDER_API_KEY: dict[str, str] = {
    "google": "GOOGLE_API_KEY",
    "google-gla": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def required_api_key_for(model: str) -> str | None:
    """Return the env-var name that must be set for `model`, or None if unknown."""
    provider = model.split(":", 1)[0]
    return _PROVIDER_API_KEY.get(provider)
