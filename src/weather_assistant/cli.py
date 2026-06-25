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


async def _run_turn(
    user_text: str,
    deps: Deps,
    history: list[ModelMessage],
) -> list[ModelMessage]:
    async with agent.run_stream(user_text, deps=deps, message_history=history) as result:
        async for delta in result.stream_text(delta=True):
            sys.stdout.write(delta)
            sys.stdout.flush()
        sys.stdout.write("\n")
    return result.all_messages()


async def main() -> None:
    # The GOOGLE_API_KEY check has moved to __main__.py so it fires before
    # agent.py is imported (the Agent constructor would otherwise crash first).
    logger.info("starting REPL")
    print("I'm your weather assistant. Ask about the weather anywhere. Type 'quit' or 'exit' to leave.\n")

    history: list[ModelMessage] = []
    async with httpx.AsyncClient() as http:
        deps = Deps(http=http)
        while True:
            try:
                user_text = (await _read_line(PROMPT)).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                logger.info("session ended via EOF/SIGINT")
                return
            if not user_text:
                continue
            if user_text.lower() in QUIT_WORDS:
                logger.info("session ended via quit/exit")
                return
            logger.debug("user input: %r", user_text)
            try:
                history = await _run_turn(user_text, deps, history)
            except Exception as e:
                # One bad turn shouldn't kill the session.
                logger.debug("turn failed", exc_info=True)
                print(f"\n[error: {e.__class__.__name__}: {e}]\n", file=sys.stderr)


def run() -> None:
    """Synchronous entry point used by __main__.py and the console script."""
    asyncio.run(main())
