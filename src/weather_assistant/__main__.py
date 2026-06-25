"""Entry point: `python -m weather_assistant` or the `weather-assistant` console script.

The order here matters:
  1. load .env so GOOGLE_API_KEY is in os.environ
  2. configure logging to file (so submodules' loggers respect LOG_LEVEL / LOG_FILE)
  3. fast-fail with a friendly message if the key is still missing
  4. THEN import .cli — that triggers agent.py, which builds the
     pydantic-ai Agent at import time and would crash without the key.
"""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Log file path is configurable via LOG_FILE; default is <repo>/log/weather_assistant.log
# (anchored to __file__ so the path is stable regardless of the user's cwd).
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_FILE = _REPO_ROOT / "log" / "weather_assistant.log"

log_file = Path(os.getenv("LOG_FILE", str(DEFAULT_LOG_FILE))).resolve()
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "WARNING").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    filename=str(log_file),
    filemode="a",
)
log = logging.getLogger(__name__)
log.debug(".env loaded; LOG_LEVEL=%s; LOG_FILE=%s",
          os.getenv("LOG_LEVEL", "WARNING"), log_file)

# One-time hint to stderr so the user knows where logs are being written.
print(f"(logs → {log_file})", file=sys.stderr)

if not os.getenv("GOOGLE_API_KEY"):
    print(
        "error: GOOGLE_API_KEY is not set. Copy .env.example to .env and fill it in,\n"
        "or export GOOGLE_API_KEY in your shell.",
        file=sys.stderr,
    )
    sys.exit(1)

from .cli import run  # noqa: E402  (intentionally after env + logging setup)

if __name__ == "__main__":
    run()
