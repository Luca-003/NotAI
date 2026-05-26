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
        adempimento_submit,
        conservation_archive,
        draft_generate,
        human_review_completed,
        human_review_requested,
        pct_deposit,
        repertorio_assign,
        slot_extract,
        tax_calculate,
        visura_anpr,
        visura_telemaco,
    )
    from .common import (
        AdempimentoUnicoRequest,
        AdempimentoUnicoResult,
        ConservationRequest,
        ConservationResult,
        DraftRequest,
        DraftResult,
        HumanReviewDecision,
        HumanReviewRequest,
        HumanReviewResponse,
        PCTDepositRequest,
        PCTDepositResult,
        RepertorioRequest,
        RepertorioResult,
        SlotExtractRequest,
        SlotExtractResult,
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
    extracted_slots: dict[str, Any] = field(default_factory=dict)  # slot_name -> value
    extracted_provenance: dict[str, dict] = field(default_factory=dict)  # slot_name -> {chunk_id,...}
    extracted_abstained: list[str] = field(default_factory=list)
    draft: dict | None = None
    tax: dict | None = None
    review: dict | None = None
    # Post-firma notarile
    repertorio: dict | None = None        # {number, year, raccolta_number}
    adempimento: dict | None = None       # {protocol_id, accepted, transcription_number, voltura_number}
    conservation: dict | None = None      # {bundle_uri, bundle_sha256, retention_until}
    # Post-firma legale
    pct: dict | None = None               # {envelope_id, court_id, receipt_iuv, protocol_number}


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
            {
                "source": r.source,
                "found": r.found,
                "hash": r.hash,
                "summary": (r.payload or {}).get("_summary", ""),
                "data": {
                    k: v
                    for k, v in (r.payload or {}).items()
                    if k not in {"_meta", "_summary"}
                },
            }
            for r in visure_results
        ]

        # 1.5) Estrazione slot dai documenti di input gia' classificati.
        # Se non ci sono docs/classified, ritorna risultato vuoto e il draft
        # usa solo i valori del form (fallback).
        slot_res: SlotExtractResult = await workflow.execute_activity(
            slot_extract,
            SlotExtractRequest(ctx=ctx, template_id=input.template_id),
            start_to_close_timeout=timedelta(minutes=5),  # LLM extraction puo' essere lenta
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        self._state.extracted_slots = slot_res.slots
        self._state.extracted_provenance = slot_res.provenance
        self._state.extracted_abstained = slot_res.abstained

        # 2) Generazione bozza. Merge: valori estratti vincono sul form;
        # il form e' fallback per cio' che non e' stato estratto.
        self._state.status = WorkflowStatus.DRAFT_IN_CORSO.value
        merged_slots: dict[str, Any] = {
            "parties": input.parties,
            "visure_count": len(visure_results),
            "visure_summaries": self._state.visure,
            "base_imponibile": input.base_imponibile,
            "is_prima_casa": input.is_prima_casa,
            "_extracted_slot_names": list(slot_res.slots.keys()),
            "_abstained_slot_names": slot_res.abstained,
        }
        # Estratti sovrascrivono il form. Es. se l'LLM ha estratto base_imponibile
        # dal contratto preliminare, usiamo quello e non il form.
        merged_slots.update(slot_res.slots)

        draft: DraftResult = await workflow.execute_activity(
            draft_generate,
            DraftRequest(
                ctx=ctx,
                template_id=input.template_id,
                slots=merged_slots,
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

        # 3) Calcolo imposte (skippato per atti non-notarili come citazioni/decreti)
        # Determiniamo dal template_id se applicabile: legale.* / atti giudiziari skip.
        is_notarile = input.template_id.startswith("notarile.")
        if is_notarile:
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
        else:
            self._state.tax = None
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
        if decision == HumanReviewDecision.REJECTED.value:
            self._state.status = WorkflowStatus.REJECTED.value
            return {"status": self._state.status, "state": self._state.__dict__}
        if decision != HumanReviewDecision.APPROVED.value:
            self._state.status = WorkflowStatus.NEEDS_CHANGES.value
            return {"status": self._state.status, "state": self._state.__dict__}

        self._state.status = WorkflowStatus.REVIEW_COMPLETED.value

        # 7) Post-firma: branch in base al vertical.
        #    notarile.* -> repertorio + Adempimento Unico + conservazione
        #    legale.*   -> deposito PCT
        #    altri      -> stop a review_completed
        is_notarile = input.template_id.startswith("notarile.")
        is_legale = input.template_id.startswith("legale.")

        if is_legale:
            # 7-LEG) Deposito PCT (DM 44/2011 + DL 179/2012)
            draft_doc_id = (self._state.draft or {}).get("document_id")
            if not draft_doc_id:
                return {"status": self._state.status, "state": self._state.__dict__}
            pct: PCTDepositResult = await workflow.execute_activity(
                pct_deposit,
                PCTDepositRequest(
                    ctx=ctx,
                    template_id=input.template_id,
                    draft_document_id=draft_doc_id,
                    parties=input.parties,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry,
            )
            self._state.pct = {
                "envelope_id": pct.envelope_id,
                "court_id": pct.court_id,
                "receipt_iuv": pct.receipt_iuv,
                "protocol_number": pct.protocol_number,
                "deposited_at": pct.deposited_at.isoformat(),
                "accepted": pct.accepted,
            }
            self._state.status = WorkflowStatus.PCT_DEPOSITED.value
            if pct.accepted:
                self._state.status = WorkflowStatus.PCT_RECEIVED.value
            # Legale: anche qui conserviamo l'atto (procura, accordo, ricorso, ecc.)
            if self._state.draft and self._state.draft.get("document_id"):
                cons_leg: ConservationResult = await workflow.execute_activity(
                    conservation_archive,
                    ConservationRequest(
                        ctx=ctx,
                        template_id=input.template_id,
                        draft_document_id=self._state.draft["document_id"],
                    ),
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=retry,
                )
                self._state.conservation = {
                    "bundle_uri": cons_leg.bundle_uri,
                    "bundle_sha256": cons_leg.bundle_sha256,
                    "retention_until": cons_leg.retention_until.isoformat(),
                }
                self._state.status = WorkflowStatus.CONSERVATO.value
            self._state.status = WorkflowStatus.ARCHIVIATO.value
            return {"status": self._state.status, "state": self._state.__dict__}

        if not is_notarile:
            return {"status": self._state.status, "state": self._state.__dict__}

        # 7a) Numero di repertorio progressivo (L.89/1913 art. 62)
        rep: RepertorioResult = await workflow.execute_activity(
            repertorio_assign,
            RepertorioRequest(ctx=ctx, template_id=input.template_id),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )
        self._state.repertorio = {
            "number": rep.repertorio_number,
            "year": rep.repertorio_year,
            "raccolta_number": rep.raccolta_number,
        }
        self._state.status = WorkflowStatus.REPERTORIO_ASSIGNED.value

        # 7b) Adempimento Unico telematico (DPR 131/86 art. 19) - mock SOGEI
        tax_total = (self._state.tax or {}).get("total", 0.0) or 0.0
        adem: AdempimentoUnicoResult = await workflow.execute_activity(
            adempimento_submit,
            AdempimentoUnicoRequest(
                ctx=ctx,
                template_id=input.template_id,
                base_imponibile=input.base_imponibile,
                is_prima_casa=input.is_prima_casa,
                tax_total=tax_total,
                parties=input.parties,
                repertorio_number=rep.repertorio_number,
                repertorio_year=rep.repertorio_year,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )
        self._state.status = WorkflowStatus.ADEMPIMENTO_SUBMITTED.value
        self._state.adempimento = {
            "protocol_id": adem.protocol_id,
            "accepted": adem.accepted,
            "transcription_number": adem.transcription_number,
            "voltura_number": adem.voltura_number,
        }
        if adem.accepted:
            self._state.status = WorkflowStatus.ADEMPIMENTO_REGISTERED.value

        # 7c) Conservazione mock (AgID + SInCRO) - bundle su MinIO con WORM
        if self._state.draft and self._state.draft.get("document_id"):
            cons: ConservationResult = await workflow.execute_activity(
                conservation_archive,
                ConservationRequest(
                    ctx=ctx,
                    template_id=input.template_id,
                    draft_document_id=self._state.draft["document_id"],
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=retry,
            )
            self._state.conservation = {
                "bundle_uri": cons.bundle_uri,
                "bundle_sha256": cons.bundle_sha256,
                "retention_until": cons.retention_until.isoformat(),
            }
            self._state.status = WorkflowStatus.CONSERVATO.value

        self._state.status = WorkflowStatus.ARCHIVIATO.value
        return {"status": self._state.status, "state": self._state.__dict__}


ALL_WORKFLOWS = [AtoWorkflow]
