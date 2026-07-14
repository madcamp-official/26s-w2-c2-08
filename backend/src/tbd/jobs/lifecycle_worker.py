"""Runnable retry worker for private object retention and deletion."""

from __future__ import annotations

import argparse
import asyncio

from tbd.core.config import get_settings
from tbd.db import create_database
from tbd.services.lifecycle import StorageDeletionWorker
from tbd.storage import FilesystemStorage

DEFAULT_IDLE_POLL_SECONDS = 5.0


async def run(*, once: bool = False, idle_poll_seconds: float = DEFAULT_IDLE_POLL_SECONDS) -> None:
    """Run storage deletion retries with the local private-storage adapter."""

    settings = get_settings()
    database = create_database(settings)
    worker = StorageDeletionWorker(
        database.session_factory,
        FilesystemStorage(settings.storage_root),
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
    parser = argparse.ArgumentParser(description="Run the private storage deletion worker.")
    parser.add_argument(
        "--once", action="store_true", help="Process at most one ledger row, then exit."
    )
    parser.add_argument(
        "--idle-poll-seconds",
        type=float,
        default=DEFAULT_IDLE_POLL_SECONDS,
        help="Seconds to wait when no deletion is due (default: 5.0).",
    )
    args = parser.parse_args()
    if args.idle_poll_seconds <= 0:
        parser.error("--idle-poll-seconds must be greater than zero")
    asyncio.run(run(once=args.once, idle_poll_seconds=args.idle_poll_seconds))


if __name__ == "__main__":
    main()
