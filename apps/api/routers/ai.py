"""Endpoint /api/v1/ai/* - inferenza AI con vincolo zero-allucinazione.

Pattern uniforme estratto in `_execute_ai_endpoint`:
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

from typing import Any, Type, cast

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import DbDep, TenantDep, TenantPrincipal
from apps.api.deps_modules import module_required
from notai.config import get_settings
from notai.contexts.ai.abstention import AbstentionDecision, evaluate
from notai.contexts.ai.llm_gateway import LLMCallSpec, llm_gateway
from notai.contexts.ai.rag import RetrievedChunk, known_citations, retrieve
from notai.contexts.ai.schemas import (
    ClauseClassification,
    DraftSuggestion,
    StructuredAIOutput,
)
from notai.contexts.audit.logger import audit_logger

router = APIRouter(prefix="/ai", tags=["ai"])


class ClassifyClauseRequest(BaseModel):
    clause_text: str = Field(..., min_length=10, max_length=5000)
    act_kind: str | None = None
    stream_id: str | None = Field(
        None, description="Stream audit a cui agganciare la chiamata (es. act:UUID)"
    )


class DraftSuggestionRequest(BaseModel):
    base_clause: str = Field(..., min_length=10, max_length=5000)
    instruction: str = Field(..., min_length=5, max_length=2000)
    act_kind: str | None = None
    stream_id: str | None = None


def _format_context(chunks: list[RetrievedChunk], query: str) -> str:
    if not chunks:
        return f"DOMANDA:\n{query}\n\nCONTESTO NORMATIVO: nessuna fonte rilevante trovata."
    refs = "\n\n".join(
        f"[{c.citation}] (score={c.score:.2f})\n{c.text}" for c in chunks
    )
    return (
        f"DOMANDA:\n{query}\n\n"
        f"FONTI NORMATIVE DISPONIBILI (puoi citare SOLO queste in source_refs):\n{refs}"
    )


async def _execute_ai_endpoint(
    *,
    session: AsyncSession,
    principal: TenantPrincipal,
    stream_id: str | None,
    endpoint_name: str,
    role: str,
    system: str,
    response_schema: Type[StructuredAIOutput],
    retrieval_query: str,
    abstention_input_context: str,
    prompt_template_id: str,
    act_kind: str | None,
) -> dict[str, Any]:
    """Pattern uniforme: RAG + prompt + LLM + abstention + audit.

    Estrae il codice duplicato tra classify-clause e draft-suggestion.
    """
    settings = get_settings()
    stream = stream_id or f"ai-debug:{principal.tenant_id}"

    chunks = await retrieve(
        retrieval_query,
        top_k=settings.ai.rag_top_k,
        min_score=settings.ai.rag_min_score,
    )
    citations_in_kb = await known_citations()

    user = _format_context(chunks, retrieval_query)
    if act_kind:
        user += f"\n\nTipo atto: {act_kind}"

    spec = LLMCallSpec(
        tenant_id=principal.tenant_id,
        stream_id=stream,
        role=role,
        system=system,
        user=user,
        response_schema=response_schema,
        actor=principal.as_actor(),
        prompt_template_id=prompt_template_id,
        prompt_template_version=1,
    )

    parsed, invocation = await llm_gateway.call_structured(session=session, spec=spec)

    # response_schema eredita sempre da StructuredAIOutput (vincolo del caller)
    parsed_typed = cast(StructuredAIOutput | None, parsed)
    decision_obj: AbstentionDecision = evaluate(
        output=parsed_typed,
        input_context=abstention_input_context,
        known_citations=citations_in_kb,
        confidence_threshold=settings.ai.confidence_threshold,
    )

    if not decision_obj.accepted:
        await audit_logger.append(
            session=session,
            tenant_id=principal.tenant_id,
            stream_id=stream,
            type="ai.abstained",
            payload={
                "endpoint": endpoint_name,
                "reasons": decision_obj.reasons,
                "signals": decision_obj.signals,
                "llm_invocation_id": str(invocation.id) if invocation else None,
            },
            actor=principal.as_actor(),
        )

    return {
        "accepted": decision_obj.accepted,
        "output": parsed.model_dump() if (decision_obj.accepted and parsed) else None,
        "abstention": {
            "abstained": not decision_obj.accepted,
            "reasons": decision_obj.reasons,
            "signals": decision_obj.signals,
        },
        "llm_invocation_id": str(invocation.id) if invocation else None,
    }


@router.post(
    "/classify-clause",
    dependencies=[module_required("ai.classify_clause"), module_required("ai.rag")],
)
async def classify_clause(
    payload: ClassifyClauseRequest, principal: TenantDep, session: DbDep
) -> dict:
    system = (
        "Sei un assistente per studi notarili italiani. Classifichi clausole "
        "giuridiche e suggerisci tag basandoti SOLO sulle fonti normative fornite. "
        "Se non sei certo o se le fonti non coprono il caso, ABSTAIN. "
        "Mai inventare riferimenti normativi che non siano in FONTI NORMATIVE DISPONIBILI."
    )
    return await _execute_ai_endpoint(
        session=session,
        principal=principal,
        stream_id=payload.stream_id,
        endpoint_name="classify-clause",
        role="classification",
        system=system,
        response_schema=ClauseClassification,
        retrieval_query=payload.clause_text,
        abstention_input_context=payload.clause_text,
        prompt_template_id="classify-clause:v1",
        act_kind=payload.act_kind,
    )


@router.post(
    "/draft-suggestion",
    dependencies=[module_required("ai.draft_suggestion"), module_required("ai.rag")],
)
async def draft_suggestion(
    payload: DraftSuggestionRequest, principal: TenantDep, session: DbDep
) -> dict:
    query = f"{payload.instruction}\n\nClausola base:\n{payload.base_clause}"
    system = (
        "Sei un assistente per redazione di clausole notarili italiane. "
        "Proponi una variazione della clausola data, citando OBBLIGATORIAMENTE "
        "almeno una fonte normativa tra quelle fornite. VIETATO inventare numeri "
        "(importi, date, codici fiscali, IBAN) che non siano gia' nella clausola "
        "base. Se la richiesta esce dal perimetro delle fonti, abstain."
    )
    return await _execute_ai_endpoint(
        session=session,
        principal=principal,
        stream_id=payload.stream_id,
        endpoint_name="draft-suggestion",
        role="generation",
        system=system,
        response_schema=DraftSuggestion,
        retrieval_query=query,
        abstention_input_context=payload.base_clause,
        prompt_template_id="draft-suggestion:v1",
        act_kind=payload.act_kind,
    )


@router.get("/kb/stats")
async def kb_stats() -> dict:
    cits = await known_citations()
    return {"normative_citations": sorted(cits), "count": len(cits)}
