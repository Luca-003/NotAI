"""LLM gateway service: tutte le call LLM passano da qui.

Responsabilita':
  - Risolvere il ruolo applicativo (es. 'generation') nel modello alias via LLMRoutingSettings
  - Chiamare LiteLLM con timeout/retry su httpx.AsyncClient singleton (pool riusato)
  - Loggare *ogni* call in audit.llm_invocations (AI Act art. 11/50)
  - Forzare structured output (JSON schema) - return parsed Pydantic
  - Calcolare confidence calibrata da logprobs quando disponibili

Note: questo gateway NON applica abstention detector - lo fa il chiamante con
`notai.contexts.ai.abstention.evaluate(...)`. Cosi' il gateway resta una
funzione pura "esegui call + audit"; la policy di accettazione e' separata.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Type, TypeVar

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


class LLMDecision(str, Enum):
    PRODUCED = "produced"
    ABSTAINED = "abstained"


class LLMCallError(Exception):
    """Errore nella chiamata LLM (timeout, schema invalid, backend down)."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class LLMCallSpec:
    """Tutti i parametri di una call LLM strutturata in un solo oggetto.

    Evita parameter sprawl su `LLMGateway.call_structured(...)`.
    """

    tenant_id: uuid.UUID
    stream_id: str
    role: str
    system: str
    user: str
    response_schema: Type[BaseModel]
    actor: str | None = None
    prompt_template_id: str | None = None
    prompt_template_version: int | None = None
    max_tokens: int = 1024
    temperature: float = 0.0
    seed: int | None = 42
    extra_kwargs: dict = field(default_factory=dict)


class LLMGateway:
    """Singleton: condivide un httpx.AsyncClient con connection pool riusato."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def _http_client(self) -> httpx.AsyncClient:
        """Lazy singleton httpx client. Riusa la connection pool tra le call."""
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    s = get_settings()
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(s.ai.llm_http_timeout),
                        limits=httpx.Limits(
                            max_connections=20, max_keepalive_connections=10
                        ),
                    )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def call_structured(
        self,
        session: AsyncSession,
        spec: LLMCallSpec,
    ) -> tuple[BaseModel | None, LLMInvocation]:
        """Esegui call structured-output e logga in audit.

        Returns:
            (parsed_pydantic_or_None, llm_invocation_db_row)
            Se il parsing fallisce ritorna (None, invocation_with_decision=ABSTAINED).
        """
        settings = get_settings()
        model_alias = resolve_role(spec.role)
        schema_json = spec.response_schema.model_json_schema()
        system_full = (
            f"{spec.system}\n\n"
            "VINCOLI OBBLIGATORI:\n"
            "1. Rispondi SOLO con JSON valido conforme allo schema fornito.\n"
            "2. Se non hai abbastanza informazioni o se la risposta richiede ragionamento "
            "non grounded nel contesto, imposta `abstain=true` con `abstain_reason`.\n"
            "3. Ogni asserzione giuridica DEVE avere almeno una fonte in `source_refs`.\n"
            "4. NON inventare numeri (importi, date, codici fiscali, IBAN).\n"
            "5. Niente testo fuori dal JSON.\n\n"
            f"JSON Schema:\n{json.dumps(schema_json, indent=2, ensure_ascii=False)}"
        )

        prompt_full = f"SYSTEM:\n{system_full}\n\nUSER:\n{spec.user}"
        ts_start = time.time()

        body: dict = {
            "model": model_alias,
            "messages": [
                {"role": "system", "content": system_full},
                {"role": "user", "content": spec.user},
            ],
            "temperature": spec.temperature,
            "max_tokens": spec.max_tokens,
            "response_format": {"type": "json_object"},
        }
        if spec.seed is not None:
            body["seed"] = spec.seed
        body.update(spec.extra_kwargs)

        url = f"{settings.litellm.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.litellm.master_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        response_raw = ""
        response_structured: dict | None = None
        decision = LLMDecision.PRODUCED.value
        abstain_reason: str | None = None
        latency_ms: int | None = None
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        parsed: BaseModel | None = None

        try:
            client = await self._http_client()
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

            try:
                response_structured = json.loads(response_raw)
            except json.JSONDecodeError as e:
                decision = LLMDecision.ABSTAINED.value
                abstain_reason = f"json_parse_error: {e}"
                response_structured = None

            if response_structured is not None:
                try:
                    parsed = spec.response_schema.model_validate(response_structured)
                    if getattr(parsed, "abstain", False):
                        decision = LLMDecision.ABSTAINED.value
                        abstain_reason = (
                            getattr(parsed, "abstain_reason", None) or "self_abstain"
                        )
                except ValidationError as e:
                    decision = LLMDecision.ABSTAINED.value
                    first_err = e.errors()[0]["msg"] if e.errors() else str(e)
                    abstain_reason = f"schema_validation_error: {first_err}"
                    parsed = None

        except httpx.HTTPError as e:
            decision = LLMDecision.ABSTAINED.value
            abstain_reason = f"backend_error: {type(e).__name__}: {e}"
            logger.warning("notai.llm.backend_error", error=str(e))
        except Exception as e:  # noqa: BLE001
            decision = LLMDecision.ABSTAINED.value
            abstain_reason = f"unexpected_error: {type(e).__name__}: {e}"
            logger.exception("notai.llm.unexpected_error")

        audit_evt = await audit_logger.append(
            session=session,
            tenant_id=spec.tenant_id,
            stream_id=spec.stream_id,
            type="llm.invoked",
            payload={
                "role": spec.role,
                "model_alias": model_alias,
                "prompt_template_id": spec.prompt_template_id,
                "prompt_template_version": spec.prompt_template_version,
                "prompt_sha256": _sha256(prompt_full),
                "response_sha256": _sha256(response_raw),
                "decision": decision,
                "abstain_reason": abstain_reason,
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            actor=spec.actor or "ai-gateway",
        )

        invocation = LLMInvocation(
            tenant_id=spec.tenant_id,
            audit_event_id=audit_evt.id,
            ts=datetime.now(timezone.utc),
            model_alias=model_alias,
            model_backend="litellm",
            model_sha256=None,
            prompt_template_id=spec.prompt_template_id,
            prompt_template_version=spec.prompt_template_version,
            prompt_rendered=prompt_full,
            response_raw=response_raw,
            response_structured=response_structured,
            temperature=spec.temperature,
            seed=spec.seed,
            max_tokens=spec.max_tokens,
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
            role=spec.role,
            model=model_alias,
            decision=decision,
            latency_ms=latency_ms,
            tokens=completion_tokens,
        )
        return parsed if decision == LLMDecision.PRODUCED.value else None, invocation


llm_gateway = LLMGateway()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Calcola embedding via LiteLLM (alias `local/embeddings`).

    Riusa il client httpx del gateway (pool condiviso).
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
    client = await llm_gateway._http_client()  # noqa: SLF001
    r = await client.post(url, json=body, headers=headers)
    r.raise_for_status()
    data = r.json()
    return [d["embedding"] for d in data.get("data", [])]


__all__ = [
    "LLMCallError",
    "LLMCallSpec",
    "LLMDecision",
    "LLMGateway",
    "embed_texts",
    "llm_gateway",
]
