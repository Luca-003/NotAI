"""Adapter SOGEI/Entratel mock - Adempimento Unico telematico.

In Fase 2.5: MOCK. Restituisce un protocollo deterministico basato sull'hash
del payload (riproducibile per test). Shape compatibile con il file XML
SOGEI per il modulo Adempimento Unico (DPR 131/86).

In Fase 5+: integrazione vera via WS Entratel + firma digitale notaio +
canale ANC. Riferimenti normativi inclusi nel payload per audit.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from notai.contexts.integrations.base import IntegrationAdapter


class SogeiAdapter(IntegrationAdapter):
    """Mock adapter per SOGEI/Entratel - Adempimento Unico."""

    name = "sogei"
    backend = "mock"

    @staticmethod
    def summarize(payload: dict) -> str:
        if not payload:
            return "non inviato"
        proto = payload.get("protocol_id", "?")
        accepted = payload.get("accepted")
        return f"protocollo {proto} ({'accettato' if accepted else 'rifiutato'})"

    async def submit_adempimento_unico(
        self,
        *,
        template_id: str,
        base_imponibile: float,
        is_prima_casa: bool,
        tax_total: float,
        parties: list[dict],
        repertorio_number: int,
        repertorio_year: int,
    ) -> dict:
        """Mock invio Adempimento Unico.

        Risposta riproducibile: protocollo derivato da hash deterministico
        dei parametri salienti (cosi' lo smoke test puo' verificare l'hash).
        """
        # Hash deterministico per riproducibilita' test
        canonical = json.dumps(
            {
                "template": template_id,
                "base": base_imponibile,
                "prima_casa": is_prima_casa,
                "tax_total": tax_total,
                "parties": [p.get("fiscal_code") or p.get("vat") or "" for p in parties],
                "rep": f"{repertorio_number}/{repertorio_year}",
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()

        # In SOGEI vero il protocollo e' tipo "20260512-A1B2C3-AGEMM-NN-2026/12345"
        protocol = (
            f"AU-{repertorio_year}-"
            f"{repertorio_number:06d}-{digest[:6].upper()}"
        )
        receipt_hash = hashlib.sha256(("receipt:" + canonical).encode()).hexdigest()

        return {
            "protocol_id": protocol,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "accepted": True,   # mock: sempre accettato
            "receipt_hash": receipt_hash,
            # Adempimento Unico include: registrazione + trascrizione + voltura
            # Numeri progressivi mock derivati dal protocollo
            "transcription_number": f"T-{repertorio_year}/{repertorio_number * 7 + 1}",
            "voltura_number": f"V-{repertorio_year}/{repertorio_number * 7 + 1}",
            "norm_ref": "DPR 131/1986 art. 19 (Adempimento Unico telematico)",
            "_meta": {"source": "sogei-mock", "version": "v1"},
        }
