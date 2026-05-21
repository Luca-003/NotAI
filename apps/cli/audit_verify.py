"""CLI: verifica l'integrita' di una catena audit.

Uso (dentro container API):
    python -m apps.cli.audit_verify --tenant <uuid> --stream <stream_id>
    python -m apps.cli.audit_verify --tenant <uuid>    # verifica tutti gli stream

Esce con codice 0 se la catena e' integra, 1 altrimenti.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from sqlalchemy import select

from notai.contexts.audit.hash_chain import verify_chain
from notai.contexts.audit.models import AuditEvent
from notai.shared.tenancy.session import scoped_session


async def _verify_stream(tenant_id: uuid.UUID, stream_id: str) -> tuple[bool, int, str]:
    async with scoped_session(tenant_id) as session:
        rows = (
            await session.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.stream_id == stream_id,
                )
                .order_by(AuditEvent.seq.asc())
            )
        ).scalars().all()

        events = [
            {
                "prev_hash": r.prev_hash,
                "hash": r.hash,
                "payload": r.payload,
                "ts": r.ts,
                "actor": r.actor,
            }
            for r in rows
        ]

    if not events:
        return True, 0, "(stream vuoto)"

    ok, bad_idx, detail = verify_chain(events)
    return ok, len(events), detail if ok else f"errore a indice {bad_idx}: {detail}"


async def _list_streams(tenant_id: uuid.UUID) -> list[str]:
    async with scoped_session(tenant_id) as session:
        rows = (
            await session.execute(
                select(AuditEvent.stream_id)
                .where(AuditEvent.tenant_id == tenant_id)
                .distinct()
            )
        ).scalars().all()
    return sorted(rows)


async def _amain() -> int:
    p = argparse.ArgumentParser(description="Verifica integrita' catena audit NotAI")
    p.add_argument("--tenant", required=True, help="Tenant UUID")
    p.add_argument("--stream", default=None, help="Stream id (es. practice:UUID). Omesso = tutti.")
    args = p.parse_args()

    tenant_id = uuid.UUID(args.tenant)
    streams = [args.stream] if args.stream else await _list_streams(tenant_id)
    if not streams:
        print(f"Nessuno stream trovato per tenant {tenant_id}")
        return 0

    overall_ok = True
    for s in streams:
        ok, n, detail = await _verify_stream(tenant_id, s)
        symbol = "OK" if ok else "KO"
        print(f"[{symbol}] {s}  ({n} eventi)  {detail}")
        if not ok:
            overall_ok = False

    return 0 if overall_ok else 1


def main() -> None:
    sys.exit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
