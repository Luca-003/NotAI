"""Endpoint di health/readiness."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter
from sqlalchemy.sql import text

from notai.config import get_settings
from notai.shared.tenancy.session import get_engine

router = APIRouter(tags=["infra"])


@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """Liveness probe: 200 finché il processo è vivo."""
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, Any]:
    """Readiness probe: verifica che le dipendenze siano raggiungibili.

    Restituisce sempre 200 con il dettaglio per servizio (così i probe non
    flappiano in fase di startup mentre i dipendenti vengono su; un orchestratore
    esterno può comunque parsare per decidere). In prod gestire con cura.
    """
    settings = get_settings()
    checks: dict[str, str] = {}

    async def _check_db() -> None:
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as e:  # noqa: BLE001
            checks["postgres"] = f"error: {type(e).__name__}"

    async def _check_http(name: str, url: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(url)
                checks[name] = "ok" if r.status_code < 500 else f"http {r.status_code}"
        except Exception as e:  # noqa: BLE001
            checks[name] = f"error: {type(e).__name__}"

    await asyncio.gather(
        _check_db(),
        _check_http("minio", f"http://{settings.minio.host}:{settings.minio.port}/minio/health/live"),
        _check_http("qdrant", f"http://{settings.qdrant.host}:{settings.qdrant.port}/readyz"),
        _check_http("litellm", f"{settings.litellm.base_url}/health/liveliness"),
        return_exceptions=False,
    )

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
