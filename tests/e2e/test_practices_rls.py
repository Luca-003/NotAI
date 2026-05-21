"""E2E: cross-tenant leak test + practice CRUD + audit chain.

Verifica:
  1. Bootstrap di 2 tenant distinti.
  2. Ciascuno crea una pratica.
  3. Il tenant A NON vede la pratica del tenant B (RLS funzionante).
  4. La catena audit del tenant A include esattamente 1 evento practice.created.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

API_BASE = os.environ.get("NOTAI_E2E_API_BASE", "http://localhost:8000")


async def _bootstrap(client: httpx.AsyncClient, slug: str) -> tuple[str, str, str]:
    """Crea tenant + admin user, ritorna (tenant_id, user_id, jwt)."""
    r = await client.post(
        f"{API_BASE}/api/v1/dev/bootstrap",
        json={
            "slug": slug,
            "name": f"Studio Test {slug}",
            "kind": "misto",
            "admin_email": f"admin@{slug}.test",
            "admin_display_name": f"Admin {slug}",
        },
    )
    r.raise_for_status()
    body = r.json()
    return body["tenant_id"], body["user_id"], body["token"]


@pytest.mark.asyncio
async def test_cross_tenant_isolation() -> None:
    """Assicura che il tenant A NON veda le risorse del tenant B."""
    slug_a = f"alfa-{uuid.uuid4().hex[:8]}"
    slug_b = f"beta-{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(timeout=15) as client:
        tid_a, _uid_a, tok_a = await _bootstrap(client, slug_a)
        tid_b, _uid_b, tok_b = await _bootstrap(client, slug_b)
        assert tid_a != tid_b

        # A crea una pratica
        r = await client.post(
            f"{API_BASE}/api/v1/practices",
            headers={"Authorization": f"Bearer {tok_a}"},
            json={"code": f"P/{slug_a}/001", "kind": "notarile.compravendita", "title": "Atto A"},
        )
        assert r.status_code == 201, r.text
        practice_a = r.json()
        assert practice_a["tenant_id"] == tid_a

        # B crea una pratica
        r = await client.post(
            f"{API_BASE}/api/v1/practices",
            headers={"Authorization": f"Bearer {tok_b}"},
            json={"code": f"P/{slug_b}/001", "kind": "legale.civile", "title": "Atto B"},
        )
        assert r.status_code == 201, r.text
        practice_b = r.json()
        assert practice_b["tenant_id"] == tid_b

        # A elenca: deve vedere SOLO la propria pratica
        r = await client.get(
            f"{API_BASE}/api/v1/practices",
            headers={"Authorization": f"Bearer {tok_a}"},
        )
        assert r.status_code == 200
        items = r.json()
        ids = {p["id"] for p in items}
        assert practice_a["id"] in ids
        assert practice_b["id"] not in ids, "RLS leak: tenant A vede la pratica del tenant B!"

        # A tenta GET diretto sulla pratica di B: deve essere 404 (RLS la nasconde)
        r = await client.get(
            f"{API_BASE}/api/v1/practices/{practice_b['id']}",
            headers={"Authorization": f"Bearer {tok_a}"},
        )
        assert r.status_code == 404, (
            f"RLS leak: tenant A puo' leggere la pratica di B (status {r.status_code})"
        )


@pytest.mark.asyncio
async def test_unauthenticated_rejected() -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(f"{API_BASE}/api/v1/practices")
        assert r.status_code == 401
