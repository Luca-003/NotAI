"""Eccezioni di dominio condivise."""

from __future__ import annotations


class NotAIError(Exception):
    """Base per tutte le eccezioni di dominio NotAI."""


class TenantMissingError(NotAIError):
    """Operazione richiede un tenant_id nel contesto, ma non è settato."""


class NotFoundError(NotAIError):
    """Entità di dominio richiesta non trovata."""


class ConflictError(NotAIError):
    """Conflitto di stato / versione."""


class PermissionDeniedError(NotAIError):
    """Permessi insufficienti."""


class AIAbstentionRequired(NotAIError):
    """L'AI si è astenuta: il sistema DEVE passare la palla al professionista.

    Viene sollevata quando l'abstention detector blocca l'output LLM.
    L'orchestratore (Temporal) la cattura e apre un HumanTask.
    """

    def __init__(self, reason: str, llm_invocation_id: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.llm_invocation_id = llm_invocation_id
