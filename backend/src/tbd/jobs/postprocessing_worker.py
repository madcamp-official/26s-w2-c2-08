"""Runnable Session postprocessing coordinator and final-AI worker."""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from tbd.core.config import get_settings
from tbd.db import create_database
from tbd.providers.ai import create_ai_providers
from tbd.services.postprocessing import SessionPostprocessingWorker

DEFAULT_IDLE_POLL_SECONDS = 1.0


async def run(*, once: bool = False, idle_poll_seconds: float = DEFAULT_IDLE_POLL_SECONDS) -> None:
    """Run deterministic coordinator dependencies for local development and CI."""

    settings = get_settings()
    database = create_database(settings)
    providers = create_ai_providers(settings)
    worker = SessionPostprocessingWorker(
        database.session_factory,
        providers.llm,
        provider_timeout=timedelta(seconds=settings.postprocessing_ai_provider_timeout_seconds),
    )
    try:
        while True:
            processed = await worker.run_once()
            if once:
                return
            if not processed:
                await asyncio.sleep(idle_poll_seconds)
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Session postprocessing worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one Job, then exit.")
    parser.add_argument(
        "--idle-poll-seconds",
        type=float,
        default=DEFAULT_IDLE_POLL_SECONDS,
        help="Seconds to wait when no Job is available (default: 1.0).",
    )
    args = parser.parse_args()
    if args.idle_poll_seconds <= 0:
        parser.error("--idle-poll-seconds must be greater than zero")
    asyncio.run(run(once=args.once, idle_poll_seconds=args.idle_poll_seconds))


if __name__ == "__main__":
    main()
