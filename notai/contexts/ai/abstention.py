"""Abstention detector: gate obbligatorio davanti a OGNI output LLM verso il dominio.

Combina segnali multipli per decidere se accettare l'output o astenersi
e passare al professionista. Conservative-by-default: in caso di dubbio,
ABSTAIN.

Segnali (Fase 4 minimale; OOD detector + verifier cross-check in Fase 5+):
  1. self_abstain          - il modello ha messo `abstain=true` da solo
  2. schema_violation      - parsing/Pydantic gia' fallito (in llm_gateway -> None)
  3. missing_citations     - asserzioni giuridiche senza source_refs
  4. low_confidence        - confidence < soglia
  5. ungrounded_citations  - source_refs citate ma non presenti nel KB
  6. forbidden_numbers     - output contiene numeri che NON erano nel prompt input
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from notai.contexts.ai.schemas import StructuredAIOutput


@dataclass
class AbstentionDecision:
    """Esito del detector."""

    accepted: bool
    reasons: list[str] = field(default_factory=list)
    signals: dict[str, bool] = field(default_factory=dict)

    def add(self, key: str, triggered: bool, reason: str | None = None) -> None:
        self.signals[key] = triggered
        if triggered and reason:
            self.reasons.append(reason)


# Soglia di confidence minima accettabile (calibrabile per ruolo)
DEFAULT_CONFIDENCE_THRESHOLD = 0.55

# Regex per individuare "numeri di rilievo" (importi, date, CF, IBAN)
_NUM_PATTERNS = [
    re.compile(r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:€|EUR|euro)\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b"),                      # CF
    re.compile(r"\bIT\d{2}[A-Z]\d{22}\b"),                                          # IBAN IT
    re.compile(r"\b\d{11}\b"),                                                      # P.IVA
]


def _extract_numbers(text: str) -> set[str]:
    found: set[str] = set()
    for pat in _NUM_PATTERNS:
        for m in pat.findall(text or ""):
            found.add(m if isinstance(m, str) else str(m))
    return found


def evaluate(
    *,
    output: StructuredAIOutput | None,
    input_context: str,
    known_citations: set[str],
    requires_citations: bool = True,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> AbstentionDecision:
    """Decide se accettare `output` o astenersi.

    Args:
        output: parsed AI output (None se schema_violation a monte)
        input_context: testo grezzo del prompt input (per controllare numeri non-inventati)
        known_citations: set di citation note nel KB (es. 'art. 2643 c.c.'); se
                          una source_ref non e' qui dentro -> ungrounded
        requires_citations: se True (default per output giuridici), source_refs vuoti -> abstain
        confidence_threshold: soglia confidence
    """
    decision = AbstentionDecision(accepted=True)

    if output is None:
        decision.accepted = False
        decision.add("schema_violation", True, "schema validation failed upstream")
        return decision

    if getattr(output, "abstain", False):
        decision.accepted = False
        decision.add("self_abstain", True, output.abstain_reason or "model self-abstained")
        return decision

    # Citation grounding
    if requires_citations and not output.source_refs:
        decision.accepted = False
        decision.add("missing_citations", True, "no source_refs in output")
    else:
        decision.add("missing_citations", False)

    ungrounded = [
        ref.citation
        for ref in output.source_refs
        if ref.citation not in known_citations
    ]
    if ungrounded:
        decision.accepted = False
        decision.add(
            "ungrounded_citations",
            True,
            f"citations not found in KB: {ungrounded}",
        )
    else:
        decision.add("ungrounded_citations", False)

    # Confidence
    if output.confidence < confidence_threshold:
        decision.accepted = False
        decision.add(
            "low_confidence",
            True,
            f"confidence {output.confidence:.2f} < threshold {confidence_threshold}",
        )
    else:
        decision.add("low_confidence", False)

    # Numeri inventati: confronta i numeri nel proposed_text con quelli nel contesto
    proposed_text = getattr(output, "proposed_text", None) or ""
    input_numbers = _extract_numbers(input_context)
    output_numbers = _extract_numbers(proposed_text)
    invented = output_numbers - input_numbers
    if invented:
        decision.accepted = False
        decision.add(
            "forbidden_numbers",
            True,
            f"numeri non presenti nel contesto: {sorted(invented)}",
        )
    else:
        decision.add("forbidden_numbers", False)

    return decision


__all__ = ["AbstentionDecision", "DEFAULT_CONFIDENCE_THRESHOLD", "evaluate"]
