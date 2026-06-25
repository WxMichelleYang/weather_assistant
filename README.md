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

Default level is `INFO`, which surfaces per-turn + cumulative token usage, tool-call invocations, and session lifecycle. `DEBUG` adds every geocode/forecast HTTP round-trip; `WARNING` strips everything except actual problems (smaller log file, no operational visibility).

Type `quit` or `exit` to leave. `Ctrl-C` and `Ctrl-D` also work.

## Tests

```bash
pip install -e '.[dev]'       # adds pytest, pytest-asyncio, pytest-httpx
pytest                        # runs the suite from ./tests
```

Tier 1 coverage today: `tests/test_weather.py` (Open-Meteo geocode + forecast against mocked httpx), `tests/test_config.py` (provider→API-key mapping), `tests/test_agent_tool.py` (the `@agent.tool` wrapper's error-to-string translation). No real network or LLM calls — `pytest-httpx` intercepts httpx and the agent tool tests patch `get_weather` directly. Dummy API keys are seeded in `tests/conftest.py` so `agent.py`'s module-level `Agent(...)` constructor doesn't crash during test collection.

## Switching the model / provider

The model is chosen via the `MODEL` env var; the provider is whatever comes before the colon. No code change is needed to swap.

**Example — switch from Gemini to OpenAI's GPT-4o:**

In `.env`:

```
# was:
# MODEL=google:gemini-2.5-flash
# GOOGLE_API_KEY=your-google-ai-studio-key-here

MODEL=openai:gpt-4o
OPENAI_API_KEY=sk-...your-openai-key-here...
```

Then run as usual:

```bash
python -m weather_assistant
```

You can leave `GOOGLE_API_KEY` in `.env` too — only the key matching the active `MODEL` is read. To switch back, flip the `MODEL` line.

**Other providers:**

| Provider  | `MODEL=` example                  | Env var required    |
|-----------|-----------------------------------|---------------------|
| Google    | `google:gemini-2.5-flash`         | `GOOGLE_API_KEY`    |
| OpenAI    | `openai:gpt-4o` / `gpt-4o-mini`   | `OPENAI_API_KEY`    |
| Anthropic | `anthropic:claude-sonnet-4-6`     | `ANTHROPIC_API_KEY` |

If you set `MODEL=...` but forget the matching key, `__main__.py` fast-fails with a message naming the exact env var the chosen provider expects.

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

**Errors as tool results, not exceptions.** Bad city names, Open-Meteo 5xx, and network timeouts are returned to the model as `"Error: ..."` strings. The model apologizes and explains instead of the REPL crashing.

**Single retry on transient HTTP failures.** `weather.py` retries once with 500ms backoff on `TimeoutException`, `ConnectError`, `NetworkError`, or any 5xx response from Open-Meteo. 4xx and other exceptions don't retry (a retry wouldn't help). Catches the vast majority of flaky-network turns silently; a real outage still surfaces as a friendly "Error: weather service unavailable" to the model after the retry budget is exhausted.

**Friendly handling of LLM provider failures.** `_run_turn` wraps the model call in a try/except. If the provider is down / rate-limiting / returning errors, the full traceback goes to the log file and the user sees one line on stderr: `[the model is unavailable right now — try again in a moment.]`. The REPL keeps running. A top-level `try/except` in `main()` catches anything truly unexpected as a safety net.

**Geocode → forecast hidden inside the tool.** Open-Meteo's forecast endpoint needs lat/lon, but the LLM only sees `weather_tool(city: str)`. The two-step is internal to `weather.get_weather`.

**Conversation history threaded explicitly.** `result.all_messages()` after each turn, passed back via `message_history=` on the next `run_stream`. Multi-turn works; no hidden state.

## Stack

- Python 3.11+, fully async
- [Pydantic AI](https://ai.pydantic.dev) — agent loop and tool framework
- Gemini 2.5 Flash by default (provider-swappable)
- [Open-Meteo](https://open-meteo.com) — free, no API key
- `httpx` for HTTP, `python-dotenv` for env loading

## Known issues

**Slow startup (1–3s before the prompt appears).** Most of the wait between running `python -m weather_assistant` and seeing the `you>` prompt is spent importing Pydantic AI and constructing the Agent at module load — Pydantic AI pulls in the relevant provider SDK (`google-genai`, `openai`, or `anthropic`), and the provider client is initialized eagerly. It's not a bug, but it's noticeable. The visible wait *looks* like it happens after the welcome banner because the banner is the last thing printed before the prompt is awaited; in practice the same wait is paid during imports too.

  Mitigations exist but each has a tradeoff:
  - **Lazy Agent construction** — defer `Agent(...)` until the first turn instead of building it at module load. Shifts the wait from "before the prompt" to "after the first user input," which often *feels* faster but doesn't reduce total time.
  - **Skip Pydantic AI for a hand-rolled client** — fastest startup, but you lose the multi-provider abstraction and write the agent loop yourself.
  - **Faster Python startup** — `python -X importtime -m weather_assistant 2>importtime.log` shows the offenders; some can be deferred behind local imports inside functions.

  None are clearly worth it yet for a single-user interactive CLI. Documented here so it's a known cost, not a mystery.

## Future improvements

**Rotating log file.** The current logger uses a plain `FileHandler` in append mode, so `weather_assistant.log` grows without bound. For a long-lived install this should be swapped for `logging.handlers.RotatingFileHandler` (e.g. cap at 5 MB, keep 3 backups) or `TimedRotatingFileHandler` (e.g. roll daily, keep 7 days). One-line change in `__main__.py`'s `basicConfig` block; deferred until the file actually starts growing because the rotation policy is easier to choose once we know the real-world log volume.

**Turn-level tool-call monitor.** Today each `weather_tool` invocation gets its own `INFO` log line, and per-turn + cumulative session token usage are also logged (`turn tokens: in=… out=… total=…` and a final `cumulative tokens` line on exit). What's still missing is *which tools fired together in a turn* and how long the turn took end-to-end. A small upgrade is to emit one structured summary per REPL turn instead of the scattered lines, e.g. `turn user='weather in London and Tokyo?' tools=['weather_tool(London)', 'weather_tool(Tokyo)'] tokens=(in=341 out=87) duration_ms=1834`. Implementation: subscribe to Pydantic AI's stream events (`FunctionToolCallEvent`, `FunctionToolResultEvent`) inside `_run_turn` in `cli.py`, accumulate them, log once at the end of the turn. This gives the data needed to later answer questions like "show me turns where no tool was called when one should have been" — i.e. it's the first step toward a real eval / correctness layer (`tests/evals/` with golden cases, or Logfire integration for a hosted UI). Deferred until there's more than one tool, since routing mistakes only really show up once tools start to overlap.
