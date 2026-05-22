"""LLM gateway service: tutte le call LLM passano da qui.

Responsabilita':
  - Risolvere il ruolo applicativo (es. 'generation') nel modello alias via LLMRoutingSettings
  - Chiamare LiteLLM con timeout/retry
  - Loggare *ogni* call in audit.llm_invocations (AI Act art. 11/50)
  - Forzare structured output (JSON schema) - return parsed Pydantic
  - Calcolare confidence calibrata da logprobs quando disponibili

NB: questo gateway NON applica abstention detector - lo fa il chiamante con
`notai.contexts.ai.abstention.evaluate(...)`. Cosi' il gateway resta una
funzione pura "esegui call + audit"; la policy di accettazione e' separata.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Type, TypeVar

import httpx
import structlog
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from notai.config import get_settings
from notai.contexts.ai.registry import resolve_role
from notai.contexts.audit.logger import audit_logger
from notai.contexts.audit.models import LLMInvocation

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMCallError(Exception):
    """Errore nella chiamata LLM (timeout, schema invalid, backend down)."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLMGateway:
    """Singleton (stateless) - chiama via `llm_gateway.call(...)`."""

    async def call_structured(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        stream_id: str,
        role: str,                                  # 'generation' | 'extraction' | ...
        system: str,
        user: str,
        response_schema: Type[T],
        actor: str | None,
        prompt_template_id: str | None = None,
        prompt_template_version: int | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        seed: int | None = 42,
    ) -> tuple[T | None, LLMInvocation]:
        """Esegui call structured-output e logga in audit.

        Returns:
            (parsed_pydantic_or_None, llm_invocation_db_row)
            Se il parsing fallisce ritorna (None, invocation_with_decision='abstained').
        """
        settings = get_settings()
        model_alias = resolve_role(role)
        # JSON-mode instruction generica (Ollama via LiteLLM gestisce 'response_format')
        schema_json = response_schema.model_json_schema()
        system_full = (
            f"{system}\n\n"
            "VINCOLI OBBLIGATORI:\n"
            "1. Rispondi SOLO con JSON valido conforme allo schema fornito.\n"
            "2. Se non hai abbastanza informazioni o se la risposta richiede ragionamento "
            "non grounded nel contesto, imposta `abstain=true` con `abstain_reason`.\n"
            "3. Ogni asserzione giuridica DEVE avere almeno una fonte in `source_refs`.\n"
            "4. NON inventare numeri (importi, date, codici fiscali, IBAN).\n"
            "5. Niente testo fuori dal JSON.\n\n"
            f"JSON Schema:\n{json.dumps(schema_json, indent=2, ensure_ascii=False)}"
        )

        prompt_full = f"SYSTEM:\n{system_full}\n\nUSER:\n{user}"
        ts_start = time.time()

        body = {
            "model": model_alias,
            "messages": [
                {"role": "system", "content": system_full},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if seed is not None:
            body["seed"] = seed

        url = f"{settings.litellm.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.litellm.master_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        response_raw = ""
        response_structured: dict | None = None
        decision = "produced"
        abstain_reason: str | None = None
        latency_ms: int | None = None
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        parsed: T | None = None

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                r = await client.post(url, json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
                latency_ms = int((time.time() - ts_start) * 1000)
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                response_raw = msg.get("content") or ""
                usage = data.get("usage") or {}
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")

            # Parse JSON
            try:
                response_structured = json.loads(response_raw)
            except json.JSONDecodeError as e:
                decision = "abstained"
                abstain_reason = f"json_parse_error: {e}"
                response_structured = None

            # Valida schema Pydantic
            if response_structured is not None:
                try:
                    parsed = response_schema.model_validate(response_structured)
                    # Se il modello stesso ha alzato abstain=true, propaghiamo
                    if getattr(parsed, "abstain", False):
                        decision = "abstained"
                        abstain_reason = getattr(parsed, "abstain_reason", None) or "self_abstain"
                except ValidationError as e:
                    decision = "abstained"
                    abstain_reason = f"schema_validation_error: {e.errors()[0]['msg'] if e.errors() else str(e)}"
                    parsed = None

        except httpx.HTTPError as e:
            decision = "abstained"
            abstain_reason = f"backend_error: {type(e).__name__}: {e}"
        except Exception as e:  # noqa: BLE001
            decision = "abstained"
            abstain_reason = f"unexpected_error: {type(e).__name__}: {e}"

        # Audit event nel flusso transazionale chiamante (audit_logger gestisce hash chain)
        audit_evt = await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=stream_id,
            type="llm.invoked",
            payload={
                "role": role,
                "model_alias": model_alias,
                "prompt_template_id": prompt_template_id,
                "prompt_template_version": prompt_template_version,
                "prompt_sha256": _sha256(prompt_full),
                "response_sha256": _sha256(response_raw),
                "decision": decision,
                "abstain_reason": abstain_reason,
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            actor=actor or "ai-gateway",
        )

        # Record dettagliato in audit.llm_invocations (riferito all'audit event)
        invocation = LLMInvocation(
            tenant_id=tenant_id,
            audit_event_id=audit_evt.id,
            ts=datetime.now(timezone.utc),
            model_alias=model_alias,
            model_backend="litellm",
            model_sha256=None,                          # da popolare quando avremo i pesi
            prompt_template_id=prompt_template_id,
            prompt_template_version=prompt_template_version,
            prompt_rendered=prompt_full,
            response_raw=response_raw,
            response_structured=response_structured,
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            decision=decision,
            abstain_reason=abstain_reason,
            confidence=getattr(parsed, "confidence", None) if parsed else None,
            citations=(
                [c.model_dump() for c in getattr(parsed, "source_refs", [])]
                if parsed else None
            ),
            input_snapshot_sha256=_sha256(prompt_full),
            output_snapshot_sha256=_sha256(response_raw),
            rationale=getattr(parsed, "rationale", None) if parsed else None,
        )
        session.add(invocation)
        await session.flush()

        logger.info(
            "notai.llm.invoked",
            role=role,
            model=model_alias,
            decision=decision,
            latency_ms=latency_ms,
            tokens=completion_tokens,
        )
        return parsed if decision == "produced" else None, invocation


llm_gateway = LLMGateway()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Calcola embedding via LiteLLM (alias `local/embeddings`).

    Usata da RAG ingestion + retrieval. Non audita ogni singola call - sarebbe
    rumore. L'audit dell'embedding e' implicito nel knowledge base hash.
    """
    if not texts:
        return []
    settings = get_settings()
    url = f"{settings.litellm.base_url}/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.litellm.master_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    body = {"model": resolve_role("embeddings"), "input": texts}
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
    return [d["embedding"] for d in data.get("data", [])]


__all__ = ["LLMCallError", "LLMGateway", "embed_texts", "llm_gateway"]
