"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .db import create_db_engine, create_session_factory, ensure_database_directory
from .errors import install_error_handlers
from .middleware import RequestContextMiddleware
from .observability import configure_logging
from .ratelimit import TokenBucketRateLimiter
from .routers import capabilities, files, health, internal, internal_prep, jobs, prep, session
from .security import rate_limit
from .services.reaper import LeaseReaper
from .settings import Settings, get_settings
from .storage import LocalStorage


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    storage = LocalStorage(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_database_directory(settings)
        storage.ensure_layout()
        reaper = LeaseReaper(session_factory, settings)
        app.state.reaper = reaper
        reaper.start()
        try:
            yield
        finally:
            reaper.stop()
            engine.dispose()

    docs_enabled = settings.docs_enabled
    app = FastAPI(
        title="MD Service API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.storage = storage
    app.state.rate_limiter = TokenBucketRateLimiter(
        settings.rate_limit_requests_per_minute
    )
    app.state.login_limiter = TokenBucketRateLimiter(
        settings.web_login_attempts_per_minute
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-Request-ID",
                "X-CSRF-Token",
            ],
            expose_headers=["X-Request-ID"],
        )

    # Added after CORS so request IDs and access logs cover preflight handling
    # as well as normal requests.
    app.add_middleware(RequestContextMiddleware)

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(session.router)
    app.include_router(internal.router)
    app.include_router(internal_prep.router)

    api = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(rate_limit)],
    )
    api.include_router(capabilities.router)
    api.include_router(files.router)
    api.include_router(jobs.router)
    api.include_router(prep.router)
    app.include_router(api)
    return app


app = create_app()
