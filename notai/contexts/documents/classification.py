"""Classificazione + tagging automatico dei chunk con LLM structured output.

Pattern:
    Per ogni chunk -> LLM gateway -> ChunkClassification (con abstention).
    Per le citation normative usiamo le citation della KB normativa (RAG),
    ma per il tipo documento + entita' NON serve grounding obbligatorio
    (tipo doc deriva dalla forma testuale; entita' sono cose letteralmente
    presenti nel chunk).

Politica di abstention:
    - Se l'LLM dice abstain=true -> classifichiamo come "indeterminato"
    - Schema violation -> stesso
    - Mai blocchiamo la pipeline di ingestion: l'astensione e' un valore valido
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from notai.contexts.ai.abstention import evaluate
from notai.contexts.ai.llm_gateway import LLMCallSpec, llm_gateway
from notai.contexts.ai.rag import known_citations
from notai.contexts.ai.schemas import ChunkClassification, StructuredAIOutput
from notai.contexts.audit.logger import audit_logger
from notai.contexts.audit.streams import stream_for_document
from notai.contexts.documents.models import Document, DocumentChunk
from notai.shared.tenancy.session import scoped_session

logger = structlog.get_logger(__name__)

# Concorrenza massima delle call LLM di classificazione.
# Default 2: tiene la macchina usabile in parallelo (vs 5 che satura CPU/RAM
# con LLM 7B locale). Tunabile via env NOTAI_CLASSIFY_CONCURRENCY.
# Per chi ha GPU o usa cloud: alza a 5-10 senza problemi.
CLASSIFY_CONCURRENCY = int(os.environ.get("NOTAI_CLASSIFY_CONCURRENCY", "2"))

SYSTEM_PROMPT = (
    "Sei un classificatore di documenti per uno studio notarile italiano. "
    "Analizzi un singolo chunk di testo (puo' essere parte di una visura "
    "catastale, camerale, atto preliminare, documento d'identita', codice "
    "fiscale, perizia, certificato anagrafico). "
    "Devi:\n"
    "1. Riconoscere il `document_type` dal testo (Literal nello schema).\n"
    "2. Estrarre le `entities` letteralmente presenti nel chunk (nomi, CF, "
    "indirizzi, riferimenti catastali, importi, date). Non inventare nulla.\n"
    "3. Citare in `normative_refs` SOLO se il chunk fa esplicito riferimento "
    "a una norma (es. 'art. 2643 c.c.') E quella norma e' nel knowledge base "
    "fornito. Lista vuota se non sai.\n"
    "4. Scrivere un `summary` di 1-2 frasi del contenuto.\n"
    "5. Suggerire `suggested_tags` brevi (es. 'immobile', 'venditore', 'milano')."
    "\n\nSe il chunk e' troppo corto o ambiguo, imposta abstain=true e "
    "document_type='indeterminato'."
)


async def classify_chunk(
    session,
    *,
    tenant_id: uuid.UUID,
    chunk: DocumentChunk,
    document_filename: str,
    citations_in_kb: set[str] | None = None,
) -> ChunkClassification | None:
    """Classifica un chunk. Pre-pass euristico CPU (microsecondi); se non
    confident, fallback su LLM strutturato.

    `citations_in_kb`: se non passato, lo carichiamo qui (lento perche' fa una
    query ogni volta). Il chiamante batch DOVREBBE pre-caricarlo una volta sola.
    """
    # ---- Phase 2: pre-pass euristico ----
    from notai.contexts.documents.heuristic_classifier import classify_heuristic

    heur = classify_heuristic(document_filename, chunk.text)
    if heur is not None:
        # Confident classification senza LLM: salviamo lo stato e ritorniamo
        # ChunkClassification con entities=[] (slot_extractor lavora direttamente
        # sul chunk.text, non perde nulla).
        await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=stream_for_document(chunk.document_id),
            type="chunk.classified_by_heuristic",
            payload={
                "chunk_id": str(chunk.id),
                "ordering": chunk.ordering,
                "document_type": heur.document_type,
                "confidence": heur.confidence,
                "rationale": heur.rationale,
                "tags": list(heur.suggested_tags),
            },
            actor="heuristic-classifier",
        )
        logger.info(
            "notai.classify.heuristic_match",
            chunk_id=str(chunk.id),
            document_type=heur.document_type,
            confidence=heur.confidence,
            rationale=heur.rationale,
        )
        return ChunkClassification(
            document_type=heur.document_type,  # type: ignore[arg-type]
            entities=[],
            summary=None,
            suggested_tags=list(heur.suggested_tags),
            confidence=heur.confidence,
            abstain=False,
            rationale=f"heuristic: {heur.rationale}",
        )

    # ---- Fallback LLM ----
    user = (
        f"FILE SORGENTE: {document_filename}\n"
        f"CHUNK #{chunk.ordering}"
        f"{f' (pagina {chunk.page_number})' if chunk.page_number else ''}\n\n"
        f"---\n{chunk.text}\n---"
    )

    spec = LLMCallSpec(
        tenant_id=tenant_id,
        stream_id=stream_for_document(chunk.document_id),
        role="classification",
        system=SYSTEM_PROMPT,
        user=user,
        response_schema=ChunkClassification,
        actor="ingestion-classifier",
        prompt_template_id="chunk_classification:v1",
        prompt_template_version=1,
        # Per la classificazione un po' piu' di token (entities possono essere molti)
        max_tokens=1024,
    )

    parsed, invocation = await llm_gateway.call_structured(session=session, spec=spec)

    # Abstention detector: per i chunk NON richiediamo citation obbligatoria
    # (e' una classificazione, non una asserzione giuridica).
    if citations_in_kb is None:
        citations_in_kb = await known_citations()

    decision = evaluate(
        output=parsed if isinstance(parsed, StructuredAIOutput) else None,
        input_context=chunk.text,
        known_citations=citations_in_kb,
        requires_citations=False,           # classificazione non richiede norme
        confidence_threshold=0.0,           # accettiamo bassa confidence per estrarre
    )

    if decision.accepted and parsed is not None:
        logger.info(
            "notai.classify.chunk_ok",
            chunk_id=str(chunk.id),
            document_type=getattr(parsed, "document_type", None),
            entities_count=len(getattr(parsed, "entities", []) or []),
            invocation=str(invocation.id) if invocation else None,
        )
        return parsed  # type: ignore[return-value]

    # Abstention -> audit + ritorna None
    await audit_logger.append(
        session=session,
        tenant_id=tenant_id,
        stream_id=stream_for_document(chunk.document_id),
        type="chunk.classification_abstained",
        payload={
            "chunk_id": str(chunk.id),
            "ordering": chunk.ordering,
            "reasons": decision.reasons,
            "signals": decision.signals,
            "llm_invocation_id": str(invocation.id) if invocation else None,
        },
        actor="ingestion-classifier",
    )
    return None


async def _classify_one_in_own_session(
    chunk_id: uuid.UUID,
    tenant_id: uuid.UUID,
    document_filename: str,
    citations_in_kb: set[str],
    sem: asyncio.Semaphore,
) -> str:
    """Classifica UN chunk in una sessione propria. Ritorna l'esito finale:
    'classified' | 'abstained' | 'failed' | 'skipped' | 'missing'.

    Sessione separata per chunk = sicuro per concorrenza (sqlalchemy async
    session non e' thread/task safe condivisa). Il semaphore limita le call
    LLM in volo per non saturare il gateway.
    """
    async with sem:
        async with scoped_session(tenant_id) as s:
            chunk = (
                await s.execute(select(DocumentChunk).where(DocumentChunk.id == chunk_id))
            ).scalar_one_or_none()
            if chunk is None:
                return "missing"
            if chunk.classification_status == "done":
                return "skipped"

            chunk.classification_status = "in_progress"
            try:
                result = await classify_chunk(
                    s,
                    tenant_id=tenant_id,
                    chunk=chunk,
                    document_filename=document_filename,
                    citations_in_kb=citations_in_kb,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("notai.classify.chunk_failed", chunk_id=str(chunk_id))
                chunk.classification_status = "failed"
                chunk.classification = {"error": f"{type(e).__name__}: {e}"}
                chunk.classified_at = datetime.now(timezone.utc)
                return "failed"

            chunk.classified_at = datetime.now(timezone.utc)
            if result is None:
                chunk.classification_status = "abstained"
                chunk.classification = {"abstained": True}
                return "abstained"
            chunk.classification_status = "done"
            chunk.classification = result.model_dump()
            return "classified"


async def classify_document_chunks(
    document_id: uuid.UUID, tenant_id: uuid.UUID
) -> dict:
    """Classifica tutti i chunk di un documento. Idempotente: salta chunk gia'
    in status='done'. Le call LLM girano in parallelo (sem=CLASSIFY_CONCURRENCY).
    """
    async with scoped_session(tenant_id) as session:
        doc = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if doc is None:
            raise ValueError(f"document {document_id} not found")

        chunks = (
            (
                await session.execute(
                    select(DocumentChunk.id, DocumentChunk.classification_status)
                    .where(DocumentChunk.document_id == document_id)
                    .order_by(DocumentChunk.ordering.asc())
                )
            )
            .all()
        )
        if not chunks:
            return {"classified": 0, "abstained": 0, "skipped": 0, "no_chunks": True}

        await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=stream_for_document(document_id),
            type="document.classification_started",
            payload={"document_id": str(document_id), "chunks_count": len(chunks)},
            actor="ingestion-classifier",
        )
        document_filename = doc.filename

    # Citations caricate una sola volta (era N volte, una per chunk).
    citations_in_kb = await known_citations()
    sem = asyncio.Semaphore(CLASSIFY_CONCURRENCY)
    outcomes = await asyncio.gather(
        *(
            _classify_one_in_own_session(
                chunk_id=row[0],
                tenant_id=tenant_id,
                document_filename=document_filename,
                citations_in_kb=citations_in_kb,
                sem=sem,
            )
            for row in chunks
        ),
        return_exceptions=False,
    )

    classified = sum(1 for o in outcomes if o == "classified")
    abstained = sum(1 for o in outcomes if o == "abstained")
    skipped = sum(1 for o in outcomes if o == "skipped")

    async with scoped_session(tenant_id) as session:

        await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=stream_for_document(document_id),
            type="document.classification_completed",
            payload={
                "document_id": str(document_id),
                "classified": classified,
                "abstained": abstained,
                "skipped": skipped,
                "total_chunks": len(chunks),
            },
            actor="ingestion-classifier",
        )

    logger.info(
        "notai.classify.done",
        document_id=str(document_id),
        classified=classified,
        abstained=abstained,
        skipped=skipped,
    )
    return {
        "document_id": str(document_id),
        "classified": classified,
        "abstained": abstained,
        "skipped": skipped,
        "total_chunks": len(chunks),
    }


# Compat con possibili import nelle activities
_ = StructuredAIOutput


__all__ = ["classify_chunk", "classify_document_chunks"]
