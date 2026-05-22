"""Workflow Temporal per il ciclo di vita di un Atto.

Stati attraversati:
    bozza -> visure_in_corso -> draft_generated -> tax_calculated ->
    review_requested -> review_completed -> firmato (signal) -> registrato

Tutti gli step long-running passano da activity (retry + timeout gestiti
da Temporal). Le decisioni umane sono signals.

Importante: il workflow DEVE essere deterministico - niente datetime.now,
niente random, niente I/O dentro la funzione `run`. Tutto cio' va in activity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

# Tutti gli import non-Temporal vanno passati per `workflow.unsafe.imports_passed_through`
# ma i nostri dataclass condivisi sono safe (no I/O).
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
        HumanReviewRequest,
        HumanReviewResponse,
        TaxCalculationRequest,
        VisuraRequest,
        VisuraResult,
        WorkflowContext,
    )


@dataclass
class AtoWorkflowInput:
    """Input iniziale del workflow Atto."""

    ctx: WorkflowContext
    template_id: str
    base_imponibile: float
    is_prima_casa: bool
    parties: list[dict] = field(default_factory=list)
    # Ogni party: {"role": "venditore", "fiscal_code": "...", "vat": "..."}


@dataclass
class AtoWorkflowState:
    """Stato esposto via query handler (sola lettura)."""

    status: str = "bozza"
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

        # 1) Visure su tutte le parti
        self._state.status = "visure_in_corso"
        visure_results: list[VisuraResult] = []
        for party in input.parties:
            req = VisuraRequest(
                ctx=ctx,
                party_fiscal_code=party.get("fiscal_code"),
                party_vat=party.get("vat"),
            )
            # Una persona giuridica -> Telemaco; persona fisica -> ANPR
            if party.get("kind") == "PG" or party.get("vat"):
                act_fn = visura_telemaco
            else:
                act_fn = visura_anpr
            res: VisuraResult = await workflow.execute_activity(
                act_fn,
                req,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry,
            )
            visure_results.append(res)
            self._state.visure.append({
                "source": res.source,
                "found": res.found,
                "hash": res.hash,
            })

        # 2) Generazione bozza
        self._state.status = "draft_in_corso"
        draft_req = DraftRequest(
            ctx=ctx,
            template_id=input.template_id,
            slots={
                "parties": input.parties,
                "visure_count": len(visure_results),
                "base_imponibile": input.base_imponibile,
            },
        )
        draft: DraftResult = await workflow.execute_activity(
            draft_generate,
            draft_req,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=retry,
        )
        self._state.draft = {
            "document_id": draft.document_id,
            "sha256": draft.sha256,
            "storage_uri": draft.storage_uri,
        }
        self._state.status = "draft_generated"

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
        self._state.status = "tax_calculated"

        # 4) Apri HumanTask di review
        self._state.status = "review_requested"
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
            self._state.status = "review_timeout"
            return {"status": "review_timeout", "state": self._state.__dict__}

        if self._cancelled:
            self._state.status = "cancelled"
            return {"status": "cancelled", "state": self._state.__dict__}

        # 6) Registra l'esito del review (e' arrivato il signal)
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

        if self._review_response.decision == "approved":
            self._state.status = "review_completed"
            # Fase 2 si ferma qui: la firma (smart card) richiede client desktop.
            # In Fase 3 collegheremo l'endpoint che riceve il file firmato.
            return {"status": "review_completed", "state": self._state.__dict__}
        elif self._review_response.decision == "rejected":
            self._state.status = "rejected"
            return {"status": "rejected", "state": self._state.__dict__}
        else:
            self._state.status = "needs_changes"
            return {"status": "needs_changes", "state": self._state.__dict__}


ALL_WORKFLOWS = [AtoWorkflow]
