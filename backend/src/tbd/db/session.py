"""Async SQLAlchemy resources owned by one FastAPI application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tbd.core.config import Settings


@dataclass(frozen=True)
class Database:
    """Engine and session factory with explicit lifecycle ownership."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def check_connection(self) -> None:
        """Run the lightweight query used by the readiness endpoint."""

        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """Close pooled database connections during application shutdown."""

        await self.engine.dispose()


def create_database(settings: Settings) -> Database:
    """Create a database resource without opening a connection eagerly."""

    engine = create_async_engine(
        settings.effective_database_url,
        pool_pre_ping=True,
    )
    return Database(
        engine=engine,
        session_factory=async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        ),
    )


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Provide the transaction boundary that services and jobs own explicitly."""

    async with session.begin():
        yield session
