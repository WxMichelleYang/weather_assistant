# weather_assistant

Command-line weather assistant powered by an LLM. Ask in natural language; the model calls a weather tool, fetches live data from Open-Meteo, and streams a friendly response back to your terminal token-by-token. Multiple cities in one question fan out as parallel tool calls.

## Setup

```bash
python3 -m venv .venv              # create an isolated virtual environment
source .venv/bin/activate          # activate it (zsh/bash on macOS/Linux)
pip install -e .                   # install deps + this package into the venv

cp .env.example .env               # then put your GOOGLE_API_KEY in .env

python -m weather_assistant        # or just: weather-assistant
```

Run `deactivate` to leave the venv. In a new shell, re-activate with `source .venv/bin/activate`.

Logs are written to `log/weather_assistant.log` (next to `src/`; override with `LOG_FILE=/some/path`). To see what the agent is doing under the hood, bump the log level:

```bash
LOG_LEVEL=DEBUG python -m weather_assistant
tail -f log/weather_assistant.log     # in another terminal
```

`DEBUG` shows every geocode/forecast HTTP round-trip; `INFO` shows tool invocations and session lifecycle; default `WARNING` keeps the log file small.

Type `quit` or `exit` to leave. `Ctrl-C` and `Ctrl-D` also work.

## Example

```
you> what's the weather in London and Tokyo right now?
London is 18°C with light winds and overcast skies. Tokyo is warmer at 27°C,
clear and a bit breezier. …
you> how about San Francisco?
…
you> quit
```

## Design decisions

**Pydantic AI over hand-rolled.** The agent loop (model → tool calls → tool results → resume) is short but fiddly across providers. Pydantic AI runs that loop, normalizes tool calls, and dispatches parallel calls automatically. Adding another tool later is one decorated function.

**Multi-provider via env var, not abstraction.** Default model is `google:gemini-2.5-flash`. Switching to `openai:gpt-4o` or `anthropic:claude-sonnet-4-6` is `MODEL=openai:gpt-4o` in `.env` plus the corresponding API key — no code change. `config.py` maps each provider prefix to the env var its pydantic-ai provider expects, so the fast-fail message in `__main__.py` always names the right key.

**Three modules, one job each.** `weather.py` knows Open-Meteo, `agent.py` knows the LLM and the tool, `cli.py` knows the terminal. No layer reaches across.

**Fully async, no blocking calls in coroutines.** `httpx.AsyncClient` for HTTP. `asyncio.to_thread(input, ...)` for stdin so the event loop stays free while tool calls are in flight.

**Token-by-token streaming.** `result.stream_text(delta=True)` yields only new tokens; each one is written and `flush()`ed immediately.

**Errors as tool results, not exceptions.** Bad city names, Open-Meteo 5xx, and network timeouts are returned to the model as `"Error: ..."` strings. The model apologizes and explains instead of the REPL crashing. A top-level `try/except` in the REPL catches anything else so a bad turn never kills the session.

**Geocode → forecast hidden inside the tool.** Open-Meteo's forecast endpoint needs lat/lon, but the LLM only sees `weather_tool(city: str)`. The two-step is internal to `weather.get_weather`.

**Conversation history threaded explicitly.** `result.all_messages()` after each turn, passed back via `message_history=` on the next `run_stream`. Multi-turn works; no hidden state.

## Stack

- Python 3.11+, fully async
- [Pydantic AI](https://ai.pydantic.dev) — agent loop and tool framework
- Gemini 2.5 Flash by default (provider-swappable)
- [Open-Meteo](https://open-meteo.com) — free, no API key
- `httpx` for HTTP, `python-dotenv` for env loading

## Future improvements

**Rotating log file.** The current logger uses a plain `FileHandler` in append mode, so `weather_assistant.log` grows without bound. For a long-lived install this should be swapped for `logging.handlers.RotatingFileHandler` (e.g. cap at 5 MB, keep 3 backups) or `TimedRotatingFileHandler` (e.g. roll daily, keep 7 days). One-line change in `__main__.py`'s `basicConfig` block; deferred until the file actually starts growing because the rotation policy is easier to choose once we know the real-world log volume.
