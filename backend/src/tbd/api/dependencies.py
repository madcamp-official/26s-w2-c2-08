"""Request-scoped dependencies shared by API routers."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.db import Database


def get_database(request: Request) -> Database:
    """Return the database resource owned by the current application."""

    return request.app.state.database


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a session without assigning commit ownership to the router."""

    database = get_database(request)
    async with database.session_factory() as session:
        yield session
