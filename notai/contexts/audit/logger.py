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
from sqlalchemy import text
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

        # UPSERT atomico sulla head: ci da' (last_seq, last_hash) attuali in una
        # singola statement, gestisce sia il caso "stream nuovo" che "stream
        # esistente", e tiene il row lock per il resto della transazione.
        # Niente advisory lock, niente SELECT scan su audit_events.
        result = await session.execute(
            text(
                f"""
                INSERT INTO {AUDIT_SCHEMA}.audit_stream_heads
                    (tenant_id, stream_id, last_seq, last_hash, updated_at)
                VALUES (:tid, :sid, 0, :genesis, :ts)
                ON CONFLICT (tenant_id, stream_id) DO UPDATE
                  SET last_seq = {AUDIT_SCHEMA}.audit_stream_heads.last_seq
                RETURNING last_seq, last_hash
                """
            ),
            {
                "tid": tenant_id,
                "sid": stream_id,
                "genesis": GENESIS_HASH,
                "ts": ts,
            },
        )
        row = result.one()
        prev_hash = row.last_hash
        next_seq = row.last_seq + 1

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

        # Aggiorna la head con (new_seq, new_hash). La row e' gia' lockata.
        await session.execute(
            text(
                f"""
                UPDATE {AUDIT_SCHEMA}.audit_stream_heads
                SET last_seq = :seq, last_hash = :hash, updated_at = :ts
                WHERE tenant_id = :tid AND stream_id = :sid
                """
            ),
            {
                "tid": tenant_id,
                "sid": stream_id,
                "seq": next_seq,
                "hash": h,
                "ts": ts,
            },
        )
        await session.flush()

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
