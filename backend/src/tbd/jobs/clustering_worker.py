"""Runnable polling process for fenced LIVE Question clustering Jobs."""

from __future__ import annotations

import argparse
import asyncio

from tbd.core.config import get_settings
from tbd.db import create_database
from tbd.providers.ai import create_ai_providers
from tbd.services.clustering import QuestionClusteringWorker

DEFAULT_IDLE_POLL_SECONDS = 1.0


async def run(
    *,
    once: bool = False,
    idle_poll_seconds: float = DEFAULT_IDLE_POLL_SECONDS,
) -> None:
    """Run the local deterministic clustering worker as a separate process."""

    settings = get_settings()
    database = create_database(settings)
    providers = create_ai_providers(settings)
    worker = QuestionClusteringWorker(
        database.session_factory,
        providers.question_clustering,
    )
    try:
        while True:
            claimed = await worker.run_once()
            if once:
                return
            if not claimed:
                await asyncio.sleep(idle_poll_seconds)
    finally:
        await database.dispose()


def main() -> None:
    """Start the standalone local Question clustering worker."""

    parser = argparse.ArgumentParser(description="Run the LIVE Question clustering worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one queued clustering Job, then exit.",
    )
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
