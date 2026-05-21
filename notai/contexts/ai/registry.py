"""LLM registry: discovery dei modelli disponibili e mappa ruolo -> modello.

Sorgenti di discovery:
  - LiteLLM:  GET /v1/models  -> elenco di alias esposti dal gateway
  - Ollama:   GET /api/tags    -> elenco di modelli installati sull'host

Il routing (ruolo -> alias) e' in Settings.llm_routing (env-based in Fase 0).
In Fase 1 diventera' DB-persisted per-tenant e modificabile via UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from notai.config import LLMRoutingSettings, get_settings

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DiscoveredModel:
    """Modello scoperto su un backend LLM."""

    name: str
    backend: str  # "litellm" | "ollama"
    size_bytes: int | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    raw: dict[str, Any] | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "backend": self.backend,
            "size_bytes": self.size_bytes,
            "family": self.family,
            "parameter_size": self.parameter_size,
            "quantization": self.quantization,
        }


async def discover_litellm_models(base_url: str, master_key: str) -> list[DiscoveredModel]:
    """Chiama GET /v1/models su LiteLLM. Ritorna lista (vuota su errore)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{base_url}/v1/models",
                headers={"Authorization": f"Bearer {master_key}"},
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            return [
                DiscoveredModel(name=m["id"], backend="litellm", raw=m)
                for m in data
                if "id" in m
            ]
    except Exception as e:  # noqa: BLE001
        logger.warning("notai.llm.discover.litellm_failed", error=str(e))
        return []


async def discover_ollama_models(base_url: str) -> list[DiscoveredModel]:
    """Chiama GET /api/tags su Ollama. Ritorna lista (vuota se Ollama non raggiungibile)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{base_url}/api/tags")
            r.raise_for_status()
            models = r.json().get("models", [])
            out: list[DiscoveredModel] = []
            for m in models:
                details = m.get("details") or {}
                out.append(
                    DiscoveredModel(
                        name=m.get("name", "?"),
                        backend="ollama",
                        size_bytes=m.get("size"),
                        family=details.get("family"),
                        parameter_size=details.get("parameter_size"),
                        quantization=details.get("quantization_level"),
                        raw=m,
                    )
                )
            return out
    except Exception as e:  # noqa: BLE001
        logger.warning("notai.llm.discover.ollama_failed", error=str(e))
        return []


async def discover_all() -> list[DiscoveredModel]:
    """Aggregatore: scopre tutti i modelli disponibili su tutti i backend."""
    settings = get_settings()
    litellm_models = await discover_litellm_models(
        settings.litellm.base_url, settings.litellm.master_key.get_secret_value()
    )
    ollama_models = await discover_ollama_models(settings.llm_routing.ollama_discovery_url)
    return litellm_models + ollama_models


# ---------------------------------------------------------------------------
# Routing (ruolo -> alias modello). In Fase 0 viene letto da env (Settings).
# Wrapper riusabile: cosi' quando lo sposteremo su DB cambia un solo punto.
# ---------------------------------------------------------------------------


def current_routing() -> LLMRoutingSettings:
    return get_settings().llm_routing


def resolve_role(role: str) -> str:
    """Risolve un ruolo applicativo nel suo alias di modello.

    Lancia ValueError per ruolo sconosciuto - evita silent fallback (zero-allucinazione:
    se non sappiamo che modello usare, NON inventiamo).
    """
    routing = current_routing()
    mapping = routing.as_dict()
    if role not in mapping:
        raise ValueError(f"Unknown LLM role '{role}'. Available: {sorted(mapping)}")
    return mapping[role]
