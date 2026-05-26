"""Adapter PCT mock - Processo Civile Telematico.

DM 44/2011 + art. 16 DL 179/2012: deposito telematico atti civili tramite
busta crittografata XML firmata digitalmente, inviata al ConsoliCom o
gateway equivalente (Lextel, GiustiziaIT). Restituisce ricevuta IUV +
protocollo del tribunale.

In Fase 5+ reale: integrazione con WS PCT del ConsoliCom + firma client
notaio/avvocato. Shape conforme al payload reale, gli ID sono deterministici
hash dei parametri salienti.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from notai.contexts.integrations.base import IntegrationAdapter


_COURT_KEYWORDS: dict[str, str] = {
    # Match heuristici sul testo del template / hint
    "milano": "Tribunale di Milano",
    "roma": "Tribunale di Roma",
    "torino": "Tribunale di Torino",
    "napoli": "Tribunale di Napoli",
    "venezia": "Tribunale di Venezia",
    "bologna": "Tribunale di Bologna",
}

_DEFAULT_COURT = "Tribunale ordinario (default)"


def _guess_court(template_id: str, hint: str | None) -> str:
    src = f"{template_id} {hint or ''}".lower()
    for key, name in _COURT_KEYWORDS.items():
        if key in src:
            return name
    return _DEFAULT_COURT


class PCTAdapter(IntegrationAdapter):
    name = "pct"
    backend = "mock"

    @staticmethod
    def summarize(payload: dict) -> str:
        if not payload:
            return "non depositato"
        proto = payload.get("protocol_number", "?")
        court = payload.get("court_id", "?")
        return f"protocollo {proto} presso {court}"

    async def deposit(
        self,
        *,
        template_id: str,
        draft_document_id: str,
        parties: list[dict],
        court_hint: str | None = None,
    ) -> dict:
        """Mock deposito PCT. Risposta riproducibile via hash deterministico.

        IUV format reale: 18 cifre. Qui lo deriviamo dall'hash del payload.
        """
        court_id = _guess_court(template_id, court_hint)

        canonical = json.dumps(
            {
                "template": template_id,
                "draft": draft_document_id,
                "court": court_id,
                "parties": [p.get("fiscal_code") or p.get("vat") or "" for p in parties],
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        envelope_id = f"PCT-ENV-{digest[:12].upper()}"
        # IUV: 18 cifre derivate dall'hash (numerico, padding)
        iuv = re.sub(r"\D", "", digest)[:18].ljust(18, "0")
        # Protocollo tribunale: anno + sequenziale fittizio
        year = datetime.now(timezone.utc).year
        proto = f"{year}/{int(digest[:6], 16) % 99999:05d}"
        receipt_hash = hashlib.sha256(("receipt:" + canonical).encode()).hexdigest()

        return {
            "envelope_id": envelope_id,
            "court_id": court_id,
            "receipt_iuv": iuv,
            "protocol_number": proto,
            "deposited_at": datetime.now(timezone.utc).isoformat(),
            "accepted": True,
            "receipt_hash": receipt_hash,
            "norm_ref": "DM 44/2011 art. 11 + DL 179/2012 art. 16",
            "_meta": {"source": "pct-mock", "version": "v1"},
        }
