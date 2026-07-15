"""Runnable polling process for requester-only Summary and Chat Jobs."""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from tbd.core.config import get_settings
from tbd.db import create_database
from tbd.providers.ai import create_ai_providers
from tbd.services.personal_ai import PersonalAIWorker

DEFAULT_IDLE_POLL_SECONDS = 1.0


async def run(
    *,
    once: bool = False,
    idle_poll_seconds: float = DEFAULT_IDLE_POLL_SECONDS,
) -> None:
    """Run the deterministic development worker as an independent process."""

    settings = get_settings()
    database = create_database(settings)
    providers = create_ai_providers(settings)
    worker = PersonalAIWorker(
        database.session_factory,
        providers.llm,
        providers.embedding,
        provider_timeout=timedelta(seconds=settings.personal_ai_provider_timeout_seconds),
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
    """Start the standalone personal-AI worker for local development."""

    parser = argparse.ArgumentParser(description="Run the private Summary and Chat worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one queued private AI Job, then exit.",
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
