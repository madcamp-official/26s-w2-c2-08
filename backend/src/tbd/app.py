"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from tbd.api.router import api_router
from tbd.core.config import Settings, get_settings
from tbd.core.errors import install_exception_handlers
from tbd.core.request_id import RequestIdMiddleware
from tbd.db import Database, create_database
from tbd.providers.google_oidc import GoogleOIDCClient, GoogleOIDCProvider
from tbd.realtime.hub import RealtimeHub
from tbd.realtime.publisher import RealtimeOutboxPublisher
from tbd.repositories.idempotency import IdempotencyRepository
from tbd.storage import FilesystemStorage, Storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Release pooled database connections during application shutdown."""

    publisher = app.state.realtime_publisher
    if publisher is not None:
        await publisher.start()
    try:
        yield
    finally:
        if publisher is not None:
            await publisher.stop()
    await app.state.database.dispose()


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    google_oidc_provider: GoogleOIDCProvider | None = None,
    storage: Storage | None = None,
) -> FastAPI:
    """Create the HTTP application and mount its public routers."""

    runtime_settings = settings or get_settings()
    runtime_database = database or create_database(runtime_settings)
    runtime_google_oidc_provider = google_oidc_provider or GoogleOIDCClient(runtime_settings)
    runtime_storage = storage or FilesystemStorage(runtime_settings.storage_root)
    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.database = runtime_database
    app.state.google_oidc_provider = runtime_google_oidc_provider
    app.state.storage = runtime_storage
    cipher = runtime_settings.idempotency_response_cipher
    app.state.idempotency_repository = IdempotencyRepository(cipher) if cipher is not None else None
    app.state.course_join_code_codec = runtime_settings.course_join_code_codec
    app.state.realtime_hub = RealtimeHub()
    app.state.realtime_publisher = (
        RealtimeOutboxPublisher(
            database=runtime_database,
            hub=app.state.realtime_hub,
            settings=runtime_settings,
        )
        if hasattr(runtime_database, "session_factory")
        else None
    )
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    app.include_router(api_router)
    return app
