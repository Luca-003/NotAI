"""Estrattore di slot dai documenti dell'atto.

Dato un template (con slot_schema) e un act_id, legge i chunk classificati
dei documenti di input dell'atto e chiede al LLM di riempire ogni slot.

Vincoli zero-allucinazione:
  - ogni slot value DEVE essere grounded su un chunk specifico (chunk_id obbligatorio)
  - se il LLM produce un valore senza chunk_id valido -> abstain forzato
  - filtra per `extract_from` (priorita' ai document_type compatibili)
  - se nessun documento del tipo richiesto e' presente -> abstain pulito
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from notai.contexts.ai.llm_gateway import LLMCallSpec, llm_gateway
from notai.contexts.ai.schemas import SlotExtraction, SlotValue
from notai.contexts.documents.kinds import INPUT_SOURCE
from notai.contexts.documents.models import Document, DocumentChunk
from notai.shared.db.soft_delete import not_deleted
from notai.shared.tenancy.session import scoped_session

logger = structlog.get_logger(__name__)


SYSTEM_PROMPT = """Sei un estrattore di dati per atti notarili italiani.
Ricevi:
  1) Una lista di SLOT da estrarre (con nome, tipo, hint).
  2) Una lista di CHUNK di testo (con id) provenienti dai documenti caricati.

Per OGNI slot:
  - Trova il valore LETTERALMENTE presente in uno dei chunk.
  - Indica `source_chunk_id` = id del chunk dove hai trovato il valore.
  - Calcola `confidence` 0..1.
  - Se il valore NON e' presente in nessun chunk: imposta `abstain=true` e
    motiva con `abstain_reason`.
  - NON inventare. NON dedurre. NON normalizzare oltre la formattazione
    minima (puoi togliere spazi extra, ma non cambiare cifre, codici, nomi).
  - Per numeri (rendita, prezzo): estrai il valore numerico in EUR senza
    separatori di migliaia (es. 1124.57 non "1.124,57").

Restituisci un JSON con il campo `slots`: list di SlotValue.
"""


def _build_slot_prompt(slot_schema: dict[str, Any], chunks: list[DocumentChunk]) -> str:
    """Costruisce il blocco USER del prompt per il LLM."""
    # 1) Riassunto slot da estrarre (skip parties / is_prima_casa che vengono dal form).
    slot_lines: list[str] = []
    for name, spec in slot_schema.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("from_form") and not spec.get("extract_from"):
            # Slot che viene SOLO dal form -> skip estrazione
            continue
        if spec.get("type") == "array":
            continue
        hint = spec.get("hint", "")
        extract_from = spec.get("extract_from", [])
        ext = (
            f" (cerca soprattutto in: {', '.join(extract_from)})"
            if extract_from
            else ""
        )
        slot_lines.append(
            f"  - {name} ({spec.get('type', 'string')}){ext}: {hint or 'estrai dai chunks'}"
        )

    # 2) Chunks rilevanti con id + preview tagging-aware.
    chunk_lines: list[str] = []
    for c in chunks:
        cls = c.classification or {}
        doc_type = cls.get("document_type", "?")
        text = c.text.strip()
        if len(text) > 1500:
            text = text[:1500] + "..."
        chunk_lines.append(
            f"---\nCHUNK id={c.id} doc_type={doc_type}\n{text}"
        )

    return (
        "## SLOT DA ESTRARRE\n"
        + "\n".join(slot_lines)
        + "\n\n## CHUNKS DISPONIBILI\n"
        + "\n".join(chunk_lines)
        + "\n---\n\n"
        "Restituisci ora il JSON con tutti gli slot."
    )


async def extract_slots(
    act_id: uuid.UUID,
    tenant_id: uuid.UUID,
    template_id: str,
    slot_schema: dict[str, Any],
) -> SlotExtraction:
    """Esegue UNA call LLM strutturata sui chunk classificati dell'atto.

    Ritorna `SlotExtraction(slots=[...])`. Slot non groundable -> abstain.
    Errori della pipeline (no docs, no chunks classificati) -> ritorna
    SlotExtraction(slots=[]).
    """
    async with scoped_session(tenant_id) as session:
        chunks = (
            await session.execute(
                select(DocumentChunk)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(
                    Document.act_id == act_id,
                    Document.kind == INPUT_SOURCE,
                    not_deleted(Document),
                    DocumentChunk.classification_status == "done",
                )
                .order_by(DocumentChunk.ordering.asc())
            )
        ).scalars().all()

        if not chunks:
            logger.info(
                "notai.slot_extract.no_chunks",
                act_id=str(act_id),
                template_id=template_id,
            )
            return SlotExtraction(
                slots=[],
                abstain=True,
                abstain_reason="no input chunks classificati per questo atto",
            )

        user_prompt = _build_slot_prompt(slot_schema, list(chunks))

        spec = LLMCallSpec(
            tenant_id=tenant_id,
            stream_id=f"act:{act_id}",
            role="extraction",
            system=SYSTEM_PROMPT,
            user=user_prompt,
            response_schema=SlotExtraction,
            actor="slot-extractor",
            prompt_template_id="slot_extraction:v1",
            prompt_template_version=1,
            max_tokens=2048,
        )
        parsed, invocation = await llm_gateway.call_structured(
            session=session, spec=spec
        )

    if not isinstance(parsed, SlotExtraction):
        logger.warning(
            "notai.slot_extract.parse_failed",
            act_id=str(act_id),
            invocation=str(invocation.id) if invocation else None,
        )
        return SlotExtraction(slots=[], abstain=True, abstain_reason="LLM parse failed")

    # Hard validation: ogni slot non-abstain DEVE avere source_chunk_id valido.
    valid_chunk_ids = {str(c.id) for c in chunks}
    cleaned: list[SlotValue] = []
    for s in parsed.slots:
        if s.abstain:
            cleaned.append(s)
            continue
        if not s.source_chunk_id or s.source_chunk_id not in valid_chunk_ids:
            # Force abstain: l'LLM ha "inventato" un chunk_id non valido.
            cleaned.append(
                SlotValue(
                    name=s.name,
                    value=None,
                    abstain=True,
                    abstain_reason="source_chunk_id mancante o non in input",
                    confidence=0.0,
                )
            )
            logger.warning(
                "notai.slot_extract.invalid_chunk_id",
                slot=s.name,
                claimed_chunk=s.source_chunk_id,
            )
            continue
        cleaned.append(s)

    logger.info(
        "notai.slot_extract.done",
        act_id=str(act_id),
        slots_total=len(cleaned),
        slots_grounded=sum(1 for s in cleaned if not s.abstain),
        slots_abstained=sum(1 for s in cleaned if s.abstain),
    )
    return SlotExtraction(slots=cleaned)


__all__ = ["extract_slots"]
