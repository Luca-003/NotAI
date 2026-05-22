"""Endpoint /api/v1/ai/* - inferenza AI con vincolo zero-allucinazione.

Pattern uniforme per tutti gli endpoint:
  1. Retrieval RAG sul query/contesto
  2. Build prompt con context grounded (top-K chunks)
  3. LLM gateway -> structured output Pydantic
  4. Abstention detector evaluate(...)
  5. Se accepted -> ritorna output con citation
     Se NON accepted -> ritorna 200 con `abstained=true` + reasons (UI apre HumanTask)

In tutti i casi, ogni call produce:
  - 1 AuditEvent type='llm.invoked' nella catena dello stream
  - 1 record audit.llm_invocations completo
  - 1 AuditEvent type='ai.abstained' se l'abstention scatta (con reasons)
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from notai.contexts.ai.abstention import evaluate
from notai.contexts.ai.llm_gateway import llm_gateway
from notai.contexts.ai.rag import known_citations, retrieve
from notai.contexts.ai.schemas import ClauseClassification, DraftSuggestion
from notai.contexts.audit.logger import audit_logger
from notai.shared.tenancy.session import scoped_session

router = APIRouter(prefix="/ai", tags=["ai"])


def _require_tenant(request: Request) -> tuple[uuid.UUID, str | None]:
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(status_code=401, detail="missing or invalid JWT")
    return tid, getattr(request.state, "user_id", None)


# ---------------------------------------------------------------------------
# Schemi request
# ---------------------------------------------------------------------------


class ClassifyClauseRequest(BaseModel):
    clause_text: str = Field(..., min_length=10, max_length=5000)
    act_kind: str | None = None
    stream_id: str | None = Field(None, description="Stream audit a cui agganciare la chiamata (es. act:UUID)")


class DraftSuggestionRequest(BaseModel):
    base_clause: str = Field(..., min_length=10, max_length=5000)
    instruction: str = Field(..., min_length=5, max_length=2000)
    act_kind: str | None = None
    stream_id: str | None = None


# ---------------------------------------------------------------------------
# Helper: format context da chunks RAG
# ---------------------------------------------------------------------------


def _format_context(chunks: list, query: str) -> str:
    if not chunks:
        return f"DOMANDA:\n{query}\n\nCONTESTO NORMATIVO: nessuna fonte rilevante trovata."
    refs = "\n\n".join(
        f"[{c.citation}] (score={c.score:.2f})\n{c.text}" for c in chunks
    )
    return (
        f"DOMANDA:\n{query}\n\n"
        f"FONTI NORMATIVE DISPONIBILI (puoi citare SOLO queste in source_refs):\n{refs}"
    )


async def _produce_or_abstain_response(
    output: Any,
    decision_obj: Any,
    invocation: Any,
) -> dict:
    """Forma standard di risposta API per gli endpoint AI."""
    return {
        "accepted": decision_obj.accepted,
        "output": output.model_dump() if (decision_obj.accepted and output) else None,
        "abstention": {
            "abstained": not decision_obj.accepted,
            "reasons": decision_obj.reasons,
            "signals": decision_obj.signals,
        },
        "llm_invocation_id": str(invocation.id) if invocation else None,
    }


# ---------------------------------------------------------------------------
# POST /api/v1/ai/classify-clause
# ---------------------------------------------------------------------------


@router.post("/classify-clause")
async def classify_clause(payload: ClassifyClauseRequest, request: Request) -> dict:
    tenant_id, actor = _require_tenant(request)

    # 1) Retrieval
    chunks = await retrieve(payload.clause_text, top_k=5)
    citations_in_kb = await known_citations()

    # 2) Prompt grounded
    system = (
        "Sei un assistente per studi notarili italiani. Classifichi clausole "
        "giuridiche e suggerisci tag basandoti SOLO sulle fonti normative fornite. "
        "Se non sei certo o se le fonti non coprono il caso, ABSTAIN. "
        "Mai inventare riferimenti normativi che non siano in FONTI NORMATIVE DISPONIBILI."
    )
    user = _format_context(chunks, payload.clause_text)
    if payload.act_kind:
        user += f"\n\nTipo atto: {payload.act_kind}"

    stream_id = payload.stream_id or f"ai-debug:{tenant_id}"

    # 3) LLM call (audit logging interno)
    async with scoped_session(tenant_id) as session:
        parsed, invocation = await llm_gateway.call_structured(
            session=session,
            tenant_id=tenant_id,
            stream_id=stream_id,
            role="classification",
            system=system,
            user=user,
            response_schema=ClauseClassification,
            actor=actor,
            prompt_template_id="classify-clause:v1",
            prompt_template_version=1,
        )

        # 4) Abstention detector
        decision_obj = evaluate(
            output=parsed,
            input_context=payload.clause_text,
            known_citations=citations_in_kb,
        )

        # 5) Audit eventuale abstention
        if not decision_obj.accepted:
            await audit_logger.append(
                session=session,
                tenant_id=tenant_id,
                stream_id=stream_id,
                type="ai.abstained",
                payload={
                    "endpoint": "classify-clause",
                    "reasons": decision_obj.reasons,
                    "signals": decision_obj.signals,
                    "llm_invocation_id": str(invocation.id) if invocation else None,
                },
                actor=actor,
            )

    return await _produce_or_abstain_response(parsed, decision_obj, invocation)


# ---------------------------------------------------------------------------
# POST /api/v1/ai/draft-suggestion
# ---------------------------------------------------------------------------


@router.post("/draft-suggestion")
async def draft_suggestion(payload: DraftSuggestionRequest, request: Request) -> dict:
    tenant_id, actor = _require_tenant(request)

    query = f"{payload.instruction}\n\nClausola base:\n{payload.base_clause}"
    chunks = await retrieve(query, top_k=5)
    citations_in_kb = await known_citations()

    system = (
        "Sei un assistente per redazione di clausole notarili italiane. "
        "Proponi una variazione della clausola data, citando OBBLIGATORIAMENTE "
        "almeno una fonte normativa tra quelle fornite. VIETATO inventare numeri "
        "(importi, date, codici fiscali, IBAN) che non siano gia' nella clausola "
        "base. Se la richiesta esce dal perimetro delle fonti, abstain."
    )
    user = _format_context(chunks, query)
    if payload.act_kind:
        user += f"\n\nTipo atto: {payload.act_kind}"

    stream_id = payload.stream_id or f"ai-debug:{tenant_id}"

    async with scoped_session(tenant_id) as session:
        parsed, invocation = await llm_gateway.call_structured(
            session=session,
            tenant_id=tenant_id,
            stream_id=stream_id,
            role="generation",
            system=system,
            user=user,
            response_schema=DraftSuggestion,
            actor=actor,
            prompt_template_id="draft-suggestion:v1",
            prompt_template_version=1,
        )

        decision_obj = evaluate(
            output=parsed,
            input_context=payload.base_clause,
            known_citations=citations_in_kb,
        )

        if not decision_obj.accepted:
            await audit_logger.append(
                session=session,
                tenant_id=tenant_id,
                stream_id=stream_id,
                type="ai.abstained",
                payload={
                    "endpoint": "draft-suggestion",
                    "reasons": decision_obj.reasons,
                    "signals": decision_obj.signals,
                    "llm_invocation_id": str(invocation.id) if invocation else None,
                },
                actor=actor,
            )

    return await _produce_or_abstain_response(parsed, decision_obj, invocation)


# ---------------------------------------------------------------------------
# Utility: GET /api/v1/ai/kb/stats
# ---------------------------------------------------------------------------


@router.get("/kb/stats")
async def kb_stats() -> dict:
    cits = await known_citations()
    return {"normative_citations": sorted(cits), "count": len(cits)}
