"""AuditLogger - service per scrivere eventi nell'audit log con hash chain.

Pattern:
    async with scoped_session() as session:
        await audit_logger.append(
            session=session,
            stream_id="practice:abc-123",
            type="practice.created",
            payload={...},
            actor=str(current_user_id),
        )
        # commit gestito da scoped_session

L'append serializza il calcolo dell'hash sotto un LOCK pessimistico sulla
(tenant_id, stream_id) per garantire la sequenzialita' della catena anche
con scritture concorrenti.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .hash_chain import GENESIS_HASH, compute_hash
from .models import AUDIT_SCHEMA, AuditEvent

logger = structlog.get_logger(__name__)


class AuditLogger:
    """Singleton di facciata. Stateless: usabile direttamente come funzione."""

    async def append(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        stream_id: str,
        type: str,
        payload: dict[str, Any],
        actor: str | None,
        timestamp_token: str | None = None,
    ) -> AuditEvent:
        """Aggiunge un evento immutabile alla catena dello stream.

        Idempotenza: NON garantita; chiamate ripetute creano eventi multipli.
        Per casi che la richiedono, il chiamante deve gestire un idempotency_key
        nel payload.

        Concurrency: usa SELECT ... FOR UPDATE su un advisory lock per
        garantire seq monotonicamente crescente e prev_hash coerente.
        """
        ts = datetime.now(timezone.utc)

        # Advisory lock per-stream per evitare race condition sull'incremento seq.
        # Hash a 64 bit dello stream id concatenato con tenant id.
        lock_key = f"{tenant_id}:{stream_id}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))").bindparams(
                bindparam("k", lock_key)
            )
        )

        # Trova l'ultimo evento dello stream (max seq + relativo hash).
        last = (
            await session.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.stream_id == stream_id,
                )
                .order_by(AuditEvent.seq.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        prev_hash = last.hash if last else GENESIS_HASH
        next_seq = (last.seq + 1) if last else 1

        h = compute_hash(prev_hash=prev_hash, payload=payload, ts=ts, actor=actor)

        evt = AuditEvent(
            tenant_id=tenant_id,
            stream_id=stream_id,
            seq=next_seq,
            ts=ts,
            type=type,
            actor=actor,
            payload=payload,
            prev_hash=prev_hash,
            hash=h,
            timestamp_token=timestamp_token,
        )
        session.add(evt)
        await session.flush()  # garantisce write subito (ma ancora dentro la tx esterna)

        logger.debug(
            "notai.audit.appended",
            tenant_id=str(tenant_id),
            stream=stream_id,
            seq=next_seq,
            type=type,
            hash=h[:12],
        )
        return evt


audit_logger = AuditLogger()


__all__ = ["AuditLogger", "audit_logger"]


# Documentation note: lo schema dei trigger anti-UPDATE/DELETE su audit.audit_events
# viene applicato dalla migration Alembic 0002 (vedi migrations/versions/0002_*.py).
# Lo schema 'audit' e' creato dall'init script Postgres 03-audit-bootstrap.sql.
_ = AUDIT_SCHEMA
