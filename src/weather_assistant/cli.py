"""Async terminal REPL. Streams tokens to stdout as they arrive."""
from __future__ import annotations

import asyncio
import logging
import sys

import httpx
from pydantic_ai.messages import ModelMessage

from .agent import Deps, agent

logger = logging.getLogger(__name__)

QUIT_WORDS = {"quit", "exit"}
PROMPT = "you> "


async def _read_line(prompt: str) -> str:
    # input() blocks; run it in a thread so the asyncio loop stays free
    # (in particular so any in-flight tool calls keep progressing).
    return await asyncio.to_thread(input, prompt)


def _extract_usage(result) -> tuple[int, int, int]:
    """Return (input, output, total) tokens for the last run.

    Defensive against pydantic-ai version drift:
      - `usage` may be a method (older) or an attribute (newer)
      - field names may be `input_tokens` / `output_tokens` (newer)
        or `request_tokens` / `response_tokens` (older)
    """
    try:
        u = result.usage
        if callable(u):
            u = u()
    except Exception:
        logger.debug("could not read usage", exc_info=True)
        return 0, 0, 0
    in_t = getattr(u, "input_tokens", None) or getattr(u, "request_tokens", 0) or 0
    out_t = getattr(u, "output_tokens", None) or getattr(u, "response_tokens", 0) or 0
    total_t = getattr(u, "total_tokens", None) or (in_t + out_t)
    return in_t, out_t, total_t


async def _run_turn(
    user_text: str,
    deps: Deps,
    history: list[ModelMessage],
) -> tuple[list[ModelMessage], tuple[int, int, int]]:
    async with agent.run_stream(user_text, deps=deps, message_history=history) as result:
        async for delta in result.stream_text(delta=True):
            sys.stdout.write(delta)
            sys.stdout.flush()
        sys.stdout.write("\n")
    tokens = _extract_usage(result)
    logger.info("turn tokens: in=%d out=%d total=%d", *tokens)
    return result.all_messages(), tokens


async def main() -> None:
    # The GOOGLE_API_KEY check has moved to __main__.py so it fires before
    # agent.py is imported (the Agent constructor would otherwise crash first).
    logger.info("starting REPL")
    print("I'm your weather assistant. Ask about the weather anywhere. Type 'quit' or 'exit' to leave.\n")

    history: list[ModelMessage] = []
    session_in = session_out = session_total = 0

    def _log_session_end(reason: str) -> None:
        logger.info(
            "session ended (%s); cumulative tokens: in=%d out=%d total=%d",
            reason, session_in, session_out, session_total,
        )

    async with httpx.AsyncClient() as http:
        deps = Deps(http=http)
        while True:
            try:
                user_text = (await _read_line(PROMPT)).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                _log_session_end("EOF/SIGINT")
                return
            if not user_text:
                continue
            if user_text.lower() in QUIT_WORDS:
                _log_session_end("quit/exit")
                return
            logger.debug("user input: %r", user_text)
            try:
                history, (in_t, out_t, tot_t) = await _run_turn(user_text, deps, history)
                session_in += in_t
                session_out += out_t
                session_total += tot_t
            except Exception as e:
                # One bad turn shouldn't kill the session.
                logger.debug("turn failed", exc_info=True)
                print(f"\n[error: {e.__class__.__name__}: {e}]\n", file=sys.stderr)


def run() -> None:
    """Synchronous entry point used by __main__.py and the console script."""
    asyncio.run(main())
