"""Unit test per l'abstention detector."""

from __future__ import annotations

import pytest

from notai.contexts.ai.abstention import evaluate
from notai.contexts.ai.schemas import (
    ClauseClassification,
    DraftSuggestion,
    SourceRef,
)


def test_self_abstain_propagates() -> None:
    out = ClauseClassification(abstain=True, abstain_reason="non lo so")
    d = evaluate(output=out, input_context="", known_citations=set())
    assert not d.accepted
    assert d.signals["self_abstain"] is True


def test_missing_citations_for_legal_output() -> None:
    out = ClauseClassification(clause_type="rinuncia_ipoteca", confidence=0.9)
    d = evaluate(output=out, input_context="", known_citations=set())
    assert not d.accepted
    assert d.signals["missing_citations"] is True


def test_ungrounded_citation_blocked() -> None:
    out = ClauseClassification(
        clause_type="x",
        confidence=0.9,
        source_refs=[SourceRef(citation="art. 9999 c.c.")],  # inesistente
    )
    d = evaluate(output=out, input_context="", known_citations={"art. 2643 c.c."})
    assert not d.accepted
    assert d.signals["ungrounded_citations"] is True


def test_grounded_high_confidence_accepted() -> None:
    out = ClauseClassification(
        clause_type="trascrizione",
        confidence=0.85,
        source_refs=[SourceRef(citation="art. 2643 c.c.", score=0.95)],
    )
    d = evaluate(output=out, input_context="", known_citations={"art. 2643 c.c."})
    assert d.accepted, d.reasons


def test_low_confidence_blocked() -> None:
    out = ClauseClassification(
        clause_type="x",
        confidence=0.30,
        source_refs=[SourceRef(citation="art. 2643 c.c.")],
    )
    d = evaluate(output=out, input_context="", known_citations={"art. 2643 c.c."})
    assert not d.accepted
    assert d.signals["low_confidence"] is True


def test_invented_amount_blocked() -> None:
    out = DraftSuggestion(
        confidence=0.9,
        source_refs=[SourceRef(citation="art. 1470 c.c.")],
        proposed_text="L'acquirente versa 250.000 EUR al venditore.",
    )
    # Il contesto NON contiene quel numero -> deve abstain
    d = evaluate(
        output=out,
        input_context="Compravendita immobiliare residenziale, prima casa.",
        known_citations={"art. 1470 c.c."},
    )
    assert not d.accepted
    assert d.signals["forbidden_numbers"] is True


def test_amount_already_in_context_passes() -> None:
    out = DraftSuggestion(
        confidence=0.9,
        source_refs=[SourceRef(citation="art. 1470 c.c.")],
        proposed_text="L'acquirente versa 250.000 EUR al venditore alla firma.",
    )
    d = evaluate(
        output=out,
        input_context="Compravendita per 250.000 EUR.",
        known_citations={"art. 1470 c.c."},
    )
    assert d.accepted, d.reasons


def test_schema_violation_when_output_none() -> None:
    d = evaluate(output=None, input_context="", known_citations=set())
    assert not d.accepted
    assert d.signals["schema_violation"] is True
