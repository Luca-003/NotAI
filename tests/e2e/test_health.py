"""E2E - verifica health/readyz contro stack containerizzato.

Richiede `docker compose -f compose.yml -f compose.dev.yml up -d` attivo.
"""

from __future__ import annotations

import os

import httpx
import pytest

API_BASE = os.environ.get("NOTAI_E2E_API_BASE", "http://localhost:8000")


@pytest.mark.asyncio
async def test_health_ok() -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(f"{API_BASE}/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_responds() -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{API_BASE}/readyz")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "checks" in body
    assert "postgres" in body["checks"]
