"""Tests for config.py — pure functions, no env/import-time side effects to mock."""
from __future__ import annotations

import pytest

from weather_assistant.config import DEFAULT_MODEL, required_api_key_for


@pytest.mark.parametrize(
    "model,expected_key",
    [
        # Known providers — provider prefix maps to its API key env var.
        ("google:gemini-2.5-flash", "GOOGLE_API_KEY"),
        ("google-gla:gemini-pro", "GOOGLE_API_KEY"),
        ("openai:gpt-4o", "OPENAI_API_KEY"),
        ("openai:gpt-4o-mini", "OPENAI_API_KEY"),
        ("anthropic:claude-sonnet-4-6", "ANTHROPIC_API_KEY"),
        # Unknown providers — return None so the fast-fail in __main__.py
        # skips, letting pydantic-ai's own error message take over.
        ("mistral:large", None),
        ("some-future-provider:xyz", None),
        ("", None),
        # No-colon edge case: split returns the whole string as the provider.
        # "openai" alone is still in the map, so it resolves; "garbage" isn't.
        ("openai", "OPENAI_API_KEY"),
        ("garbage", None),
    ],
)
def test_required_api_key_for(model, expected_key):
    assert required_api_key_for(model) == expected_key


def test_default_model_has_provider_prefix():
    # Sanity check: DEFAULT_MODEL is a "provider:model" string, otherwise
    # the fast-fail logic in __main__.py can't determine which key to require.
    assert isinstance(DEFAULT_MODEL, str)
    assert ":" in DEFAULT_MODEL
    provider = DEFAULT_MODEL.split(":", 1)[0]
    assert required_api_key_for(DEFAULT_MODEL) is not None, (
        f"DEFAULT_MODEL provider {provider!r} has no entry in _PROVIDER_API_KEY"
    )
