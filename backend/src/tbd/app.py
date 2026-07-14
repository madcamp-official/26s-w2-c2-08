"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from tbd.api.router import api_router
from tbd.core.config import Settings, get_settings
from tbd.core.errors import install_exception_handlers
from tbd.core.request_id import RequestIdMiddleware
from tbd.db import Database, create_database
from tbd.repositories.idempotency import IdempotencyRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Release pooled database connections during application shutdown."""

    yield
    await app.state.database.dispose()


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
) -> FastAPI:
    """Create the HTTP application and mount its public routers."""

    runtime_settings = settings or get_settings()
    runtime_database = database or create_database(runtime_settings)
    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.database = runtime_database
    cipher = runtime_settings.idempotency_response_cipher
    app.state.idempotency_repository = (
        IdempotencyRepository(cipher) if cipher is not None else None
    )
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    app.include_router(api_router)
    return app
