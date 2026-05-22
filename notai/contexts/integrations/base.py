"""Adapter pattern per integrazioni esterne.

Ogni integrazione (Entrate, Telemaco, ANPR, Catasto, ...) implementa una
classe che eredita da `IntegrationAdapter` ed espone metodi tipizzati.

Strategie di backend, da scegliere per adapter:
  - API ufficiale (REST/SOAP)
  - Provider commerciale (Visure.it, OpenCamere, ecc.)
  - RPA Playwright (per portali web-only)
  - Mock (per dev/test)

Tutti gli adapter loggano automaticamente le chiamate in audit via i
metodi `_audit_request/_audit_response` ereditati.
"""

from __future__ import annotations

from abc import ABC


class IntegrationAdapter(ABC):
    """Base per tutti gli adapter."""

    name: str = "base"
    backend: str = "mock"  # api | provider | rpa | mock

    def __init__(self) -> None:
        self.config: dict = {}
