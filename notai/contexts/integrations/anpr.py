"""Adapter ANPR - Anagrafe Nazionale Popolazione Residente.

In Fase 2: MOCK. Verifica del codice fiscale + restituzione dati anagrafici.
"""

from __future__ import annotations

import re

from notai.contexts.integrations.base import IntegrationAdapter

_CF_RE = re.compile(r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$")


class AnprAdapter(IntegrationAdapter):
    name = "anpr"
    backend = "mock"

    async def fetch_person_data(self, fiscal_code: str) -> dict:
        fc = (fiscal_code or "").upper().strip()
        if not _CF_RE.match(fc):
            return {}

        # Mock: dati realistici riproducibili
        return {
            "fiscal_code": fc,
            "nome": "Mario",
            "cognome": "Rossi",
            "sesso": "M",
            "data_nascita": "1970-01-01",
            "luogo_nascita": {"comune": "Roma", "provincia": "RM"},
            "residenza": {
                "via": "Via Garibaldi 5",
                "comune": "Milano",
                "cap": "20122",
                "provincia": "MI",
            },
            "stato_civile": "coniugato",
            "cittadinanza": "ITALIANA",
            "_meta": {
                "source": "anpr-mock",
                "version": "v1",
            },
        }
