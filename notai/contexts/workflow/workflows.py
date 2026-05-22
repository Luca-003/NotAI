"""Workflow Temporal per il ciclo di vita di un Atto.

Stati attraversati (WorkflowStatus enum in common.py):
    bozza -> visure_in_corso -> draft_generated -> tax_calculated ->
    review_requested -> review_completed (signal) -> ...

Tutti gli step long-running passano da activity (retry + timeout gestiti
da Temporal). Le decisioni umane sono signals.

Importante: il workflow DEVE essere deterministico - niente datetime.now,
niente random, niente I/O dentro la funzione `run`. Tutto cio' va in activity.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import (
        draft_generate,
        human_review_completed,
        human_review_requested,
        tax_calculate,
        visura_anpr,
        visura_telemaco,
    )
    from .common import (
        DraftRequest,
        DraftResult,
        HumanReviewDecision,
        HumanReviewRequest,
        HumanReviewResponse,
        TaxCalculationRequest,
        VisuraRequest,
        VisuraResult,
        WorkflowContext,
        WorkflowStatus,
    )


@dataclass
class AtoWorkflowInput:
    """Input iniziale del workflow Atto."""

    ctx: WorkflowContext
    template_id: str
    base_imponibile: float
    is_prima_casa: bool
    parties: list[dict] = field(default_factory=list)
    # Ogni party: {"role": "venditore", "kind": "PF"|"PG", "fiscal_code": "...", "vat": "..."}


@dataclass
class AtoWorkflowState:
    """Stato esposto via query handler (sola lettura)."""

    status: str = WorkflowStatus.BOZZA.value
    visure: list[dict] = field(default_factory=list)
    draft: dict | None = None
    tax: dict | None = None
    review: dict | None = None


@workflow.defn(name="AtoWorkflow")
class AtoWorkflow:
    """Workflow del ciclo di vita di un Atto (Fase 2 minimal).

    Signal `human_review_response` riceve la risposta del professionista al
    HumanTask di review della bozza generata.
    """

    def __init__(self) -> None:
        self._state = AtoWorkflowState()
        # Cache locale del signal: NON deriva dallo state perche' Temporal richiede
        # un punto fisso su cui chiamare wait_condition senza re-deserializzare il payload.
        self._review_response: HumanReviewResponse | None = None
        self._cancelled = False

    @workflow.signal(name="human_review_response")
    def receive_review(self, response: HumanReviewResponse) -> None:
        self._review_response = response

    @workflow.signal(name="cancel")
    def cancel(self) -> None:
        self._cancelled = True

    @workflow.query(name="state")
    def get_state(self) -> AtoWorkflowState:
        return self._state

    @workflow.run
    async def run(self, input: AtoWorkflowInput) -> dict[str, Any]:
        ctx = input.ctx
        retry = RetryPolicy(maximum_attempts=3)

        # 1) Visure PARALLELE su tutte le parti (asyncio.gather su execute_activity).
        # Temporal supporta gather: ogni call e' un task indipendente con retry separato.
        self._state.status = WorkflowStatus.VISURE_IN_CORSO.value
        visure_tasks = []
        for party in input.parties:
            req = VisuraRequest(
                ctx=ctx,
                party_fiscal_code=party.get("fiscal_code"),
                party_vat=party.get("vat"),
            )
            act_fn = (
                visura_telemaco
                if party.get("kind") == "PG" or party.get("vat")
                else visura_anpr
            )
            visure_tasks.append(
                workflow.execute_activity(
                    act_fn,
                    req,
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry,
                )
            )
        visure_results: list[VisuraResult] = await asyncio.gather(*visure_tasks)
        self._state.visure = [
            {"source": r.source, "found": r.found, "hash": r.hash} for r in visure_results
        ]

        # 2) Generazione bozza
        self._state.status = WorkflowStatus.DRAFT_IN_CORSO.value
        draft: DraftResult = await workflow.execute_activity(
            draft_generate,
            DraftRequest(
                ctx=ctx,
                template_id=input.template_id,
                slots={
                    "parties": input.parties,
                    "visure_count": len(visure_results),
                    "base_imponibile": input.base_imponibile,
                },
            ),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=retry,
        )
        self._state.draft = {
            "document_id": draft.document_id,
            "sha256": draft.sha256,
            "storage_uri": draft.storage_uri,
        }
        self._state.status = WorkflowStatus.DRAFT_GENERATED.value

        # 3) Calcolo imposte
        tax = await workflow.execute_activity(
            tax_calculate,
            TaxCalculationRequest(
                ctx=ctx,
                act_kind=input.template_id,
                base_imponibile=input.base_imponibile,
                is_prima_casa=input.is_prima_casa,
            ),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )
        self._state.tax = {"items": tax.items, "total": tax.total}
        self._state.status = WorkflowStatus.TAX_CALCULATED.value

        # 4) Apri HumanTask di review
        self._state.status = WorkflowStatus.REVIEW_REQUESTED.value
        await workflow.execute_activity(
            human_review_requested,
            HumanReviewRequest(
                ctx=ctx,
                title="Review bozza atto",
                description="Verifica clausole, parti e imposte prima della firma.",
                candidates=[],
            ),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )

        # 5) Attendi signal di review (max 30 giorni)
        try:
            await workflow.wait_condition(
                lambda: self._review_response is not None or self._cancelled,
                timeout=timedelta(days=30),
            )
        except TimeoutError:
            self._state.status = WorkflowStatus.REVIEW_TIMEOUT.value
            return {"status": self._state.status, "state": self._state.__dict__}

        if self._cancelled:
            self._state.status = WorkflowStatus.CANCELLED.value
            return {"status": self._state.status, "state": self._state.__dict__}

        # 6) Registra l'esito del review
        assert self._review_response is not None
        await workflow.execute_activity(
            human_review_completed,
            args=[ctx, self._review_response],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )
        self._state.review = {
            "decision": self._review_response.decision,
            "user_id": self._review_response.user_id,
        }

        decision = self._review_response.decision
        if decision == HumanReviewDecision.APPROVED.value:
            self._state.status = WorkflowStatus.REVIEW_COMPLETED.value
        elif decision == HumanReviewDecision.REJECTED.value:
            self._state.status = WorkflowStatus.REJECTED.value
        else:
            self._state.status = WorkflowStatus.NEEDS_CHANGES.value
        return {"status": self._state.status, "state": self._state.__dict__}


ALL_WORKFLOWS = [AtoWorkflow]
