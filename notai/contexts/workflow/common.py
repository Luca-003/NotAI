"""Dataclass condivisi tra workflow Temporal e activities + enum stati.

Temporal serializza tutto via DataConverter; le activity input/output
devono essere `@dataclass` o tipi primitivi. Niente SQLAlchemy model qui.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class WorkflowStatus(str, Enum):
    """Stati attraversati dall'AtoWorkflow.

    Uso str-Enum per serializzazione JSON nativa (compatibile con Temporal
    DataConverter default). Il valore stringa e' quello esposto in API/audit.
    """

    BOZZA = "bozza"
    VISURE_IN_CORSO = "visure_in_corso"
    DRAFT_IN_CORSO = "draft_in_corso"
    DRAFT_GENERATED = "draft_generated"
    TAX_CALCULATED = "tax_calculated"
    REVIEW_REQUESTED = "review_requested"
    REVIEW_COMPLETED = "review_completed"
    REVIEW_TIMEOUT = "review_timeout"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    CANCELLED = "cancelled"


class HumanReviewDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGED = "changed"


class PartyKind(str, Enum):
    PERSONA_FISICA = "PF"
    PERSONA_GIURIDICA = "PG"


@dataclass
class WorkflowContext:
    """Contesto passato a workflow e activities (tenant + actor + tracking).

    Temporal NON propaga i contextvars; passiamo esplicitamente tutto.
    """

    tenant_id: str          # UUID string (Temporal preferisce primitivi)
    act_id: str
    practice_id: str
    actor: str | None = None


@dataclass
class VisuraRequest:
    """Input per una activity di visura."""

    ctx: WorkflowContext
    party_fiscal_code: str | None = None
    party_vat: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class VisuraResult:
    """Output di una visura (mock-friendly: campi opzionali)."""

    source: str               # "telemaco" | "anpr" | "catasto" | "conservatoria" | "pra"
    found: bool
    payload: dict
    hash: str                 # SHA-256 del payload per riproducibilita'
    fetched_at: datetime


@dataclass
class SlotExtractRequest:
    ctx: WorkflowContext
    template_id: str          # template da cui leggere slot_schema


@dataclass
class SlotExtractResult:
    """Output dell'estrazione slot. `slots` chiave->valore per il render,
    `provenance` chiave->{chunk_id, char_start, char_end, confidence} per
    la value-level provenance UI.
    """
    slots: dict                  # nome_slot -> value (None se abstain)
    provenance: dict             # nome_slot -> {chunk_id, char_start, char_end, confidence}
    abstained: list[str]         # nomi degli slot per cui l'estrattore si e' astenuto


@dataclass
class DraftRequest:
    ctx: WorkflowContext
    template_id: str          # es. "notarile.compravendita.immobiliare:v1"
    slots: dict               # dati strutturati per il render


@dataclass
class DraftResult:
    document_id: str          # UUID del Document creato
    storage_uri: str
    sha256: str


@dataclass
class TaxCalculationRequest:
    ctx: WorkflowContext
    act_kind: str
    base_imponibile: float
    is_prima_casa: bool = False


@dataclass
class TaxCalculationResult:
    items: list[dict]         # lista di {tipo_imposta, aliquota, importo, riferimento_normativo}
    total: float


@dataclass
class HumanReviewRequest:
    ctx: WorkflowContext
    title: str
    description: str
    candidates: list[dict] = field(default_factory=list)


@dataclass
class HumanReviewResponse:
    decision: str             # HumanReviewDecision value
    notes: str | None = None
    user_id: str | None = None
    completed_at: datetime | None = None
    modifications: dict | None = None


def make_workflow_id(act_id: uuid.UUID | str) -> str:
    """ID workflow stabile per atto - permette signals senza handle."""
    return f"act-workflow:{act_id}"
