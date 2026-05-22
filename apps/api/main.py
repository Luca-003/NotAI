"""NotAI - FastAPI entrypoint.

In Fase 0 espone:
  - GET /health     (liveness, sempre 200 finché il processo gira)
  - GET /readyz     (readiness: pinga DB, Temporal, MinIO, OpenSearch, Qdrant)
  - GET /api/v1/me  (placeholder: ritorna il tenant del JWT, se presente)

Le route di dominio verranno aggiunte nei sprint successivi sotto /api/v1/*.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.middleware.tenancy import TenancyMiddleware
from apps.api.routers import acts, dev, health, llm, me, practices
from notai.config import get_settings

logger = structlog.get_logger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(format="%(message)s", level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _configure_logging(settings.log_level)
    logger.info("notai.api.startup", env=settings.env)
    # TODO: warmup connessioni (DB pool, Temporal client, MinIO, ecc.)
    yield
    logger.info("notai.api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NotAI API",
        version="0.1.0",
        description="Piattaforma di automazione per studi notarili e legali italiani",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TenancyMiddleware)

    app.include_router(health.router)
    app.include_router(me.router, prefix="/api/v1")
    app.include_router(llm.router, prefix="/api/v1")
    app.include_router(practices.router, prefix="/api/v1")
    app.include_router(acts.router, prefix="/api/v1")
    if settings.env == "dev":
        app.include_router(dev.router, prefix="/api/v1")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("notai.api.unhandled", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "see server logs"},
        )

    return app


app = create_app()
