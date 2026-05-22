"""Schemi Pydantic per gli output strutturati LLM.

Ogni risposta AI verso il dominio DEVE rispettare uno di questi schemi.
Convenzioni invariabili (vincolo zero-allucinazione):

  - `source_refs` obbligatorio per asserzioni giuridiche (lista di citation;
    se vuota -> abstain)
  - `confidence` 0..1 (calibrata sull'output, non valore stampato dal modello)
  - `abstain` (bool): se true il sistema NON usa l'output e apre HumanTask
  - `abstain_reason` (str): obbligatorio se abstain=true

In dominio giuridico: meglio astenersi una volta in piu' che inventare.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    """Riferimento a una fonte normativa o documentale citata dall'AI."""

    kind: Literal["normative", "internal_doc", "case_law"] = "normative"
    citation: str = Field(..., description="es. 'art. 2643 c.c.' o 'sentenza Cass. 12345/2020'")
    chunk_id: str | None = Field(None, description="ID del chunk RAG che ha fornito il testo")
    score: float | None = Field(None, ge=0, le=1)


class StructuredAIOutput(BaseModel):
    """Base comune. Ogni output AI eredita da qui."""

    abstain: bool = False
    abstain_reason: str | None = None
    confidence: float = Field(0.0, ge=0, le=1)
    source_refs: list[SourceRef] = Field(default_factory=list)
    rationale: str | None = Field(None, description="Spiegazione testuale del ragionamento")


class ClauseClassification(StructuredAIOutput):
    """Classificazione di una clausola: tipo + tag suggeriti + riferimenti normativi."""

    clause_type: str | None = Field(
        None, description="es. 'rinuncia_ipoteca_legale', 'garanzia_evizione'"
    )
    suggested_tags: list[str] = Field(default_factory=list)


class DraftSuggestion(StructuredAIOutput):
    """Suggerimento di redrafting di una clausola.

    Vincoli hard-coded:
      - `proposed_text` NON deve contenere numeri (importi/date/CF/IBAN) che non
        siano gia' presenti nel testo originale fornito come contesto.
      - Ogni asserzione giuridica deve avere source_refs.
    """

    proposed_text: str | None = None
    diff_summary: str | None = Field(None, description="Sintesi delle modifiche rispetto al testo originale")
    risk_notes: list[str] = Field(default_factory=list)


__all__ = ["ClauseClassification", "DraftSuggestion", "SourceRef", "StructuredAIOutput"]
