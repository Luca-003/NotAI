"""Adapter Telemaco/InfoCamere - visure camerali.

In Fase 2: MOCK. Restituisce dati fittizi ma con la stessa shape che ci
aspettiamo dall'API reale (per evitare refactor in Fase 2.5 quando
collegheremo l'API vera).
"""

from __future__ import annotations

from notai.contexts.integrations.base import IntegrationAdapter


class TelemacoAdapter(IntegrationAdapter):
    name = "telemaco"
    backend = "mock"

    async def fetch_company_data(self, vat_or_fiscal: str) -> dict:
        """Visura camerale per una persona giuridica.

        Shape ispirata al data model InfoCamere/Telemaco.
        """
        if not vat_or_fiscal:
            return {}

        # Mock: ritorniamo dati deterministici basati sull'hash dell'input
        # cosi' i test sono riproducibili senza essere uguali per tutti gli input.
        seed_int = sum(map(ord, vat_or_fiscal)) % 1000
        return {
            "vat_number": vat_or_fiscal if len(vat_or_fiscal) == 11 else None,
            "fiscal_code": vat_or_fiscal if len(vat_or_fiscal) == 16 else None,
            "denominazione": f"ESEMPIO SRL {seed_int:03d}",
            "forma_giuridica": "Societa' a responsabilita' limitata",
            "data_costituzione": "2018-03-12",
            "sede_legale": {
                "via": "Via Roma 10",
                "comune": "Milano",
                "cap": "20121",
                "provincia": "MI",
            },
            "capitale_sociale": 10000.00 + seed_int * 100,
            "stato": "ATTIVA",
            "amministratori": [
                {
                    "nome": "Mario",
                    "cognome": "Rossi",
                    "ruolo": "Amministratore Unico",
                    "fiscal_code": "RSSMRA70A01F205X",
                }
            ],
            "soci": [
                {
                    "denominazione": "Mario Rossi",
                    "quota_percentuale": 100.0,
                    "fiscal_code": "RSSMRA70A01F205X",
                }
            ],
            "iscrizione_rea": f"MI-{1000000 + seed_int}",
            "_meta": {
                "source": "telemaco-mock",
                "version": "v1",
            },
        }
