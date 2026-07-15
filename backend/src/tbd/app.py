"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tbd.api.router import api_router
from tbd.core.config import Settings, get_settings
from tbd.core.errors import install_exception_handlers
from tbd.core.request_id import RequestIdMiddleware
from tbd.db import Database, create_database
from tbd.providers.ai import LLMProvider, create_ai_providers
from tbd.providers.google_oidc import GoogleOIDCClient, GoogleOIDCProvider
from tbd.providers.stt import StreamingSTTProvider, create_stt_providers
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
    streaming_stt_provider: StreamingSTTProvider | None = None,
    llm_provider: LLMProvider | None = None,
) -> FastAPI:
    """Create the HTTP application and mount its public routers."""

    runtime_settings = settings or get_settings()
    runtime_database = database or create_database(runtime_settings)
    runtime_google_oidc_provider = google_oidc_provider or GoogleOIDCClient(runtime_settings)
    runtime_storage = storage or FilesystemStorage(runtime_settings.storage_root)
    runtime_ai_providers = create_ai_providers(runtime_settings)
    runtime_stt_providers = create_stt_providers(runtime_settings)
    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.database = runtime_database
    app.state.google_oidc_provider = runtime_google_oidc_provider
    app.state.storage = runtime_storage
    # Test callers may override only the synchronous Question draft adapter.
    # Every default comes from the same Settings-backed provider factory used
    # by the standalone workers.
    app.state.llm_provider = llm_provider or runtime_ai_providers.llm
    app.state.streaming_stt_provider = streaming_stt_provider or runtime_stt_providers.streaming
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
    # Media elements issue their own requests.  Keep their credentialed
    # cross-origin playback boundary aligned with the exact frontend origins
    # already trusted for browser state-changing requests; never use `*` here.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "Idempotency-Key",
            "Range",
            "Upload-Offset",
            "X-Chunk-SHA256",
            "X-Request-ID",
        ],
        expose_headers=[
            "Accept-Ranges",
            "Content-Length",
            "Content-Range",
            "X-Request-ID",
        ],
    )
    install_exception_handlers(app)
    app.include_router(api_router)
    return app
