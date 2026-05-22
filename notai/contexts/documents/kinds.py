"""Costanti per `Document.kind`.

Postgres salva ancora una `String(64)` (no enum DB) per non bloccare evoluzioni
future. Ma il codice applicativo usa SOLO questi simboli, mai i literal string.
"""

from __future__ import annotations

from typing import Final, Literal

# Documento di input caricato dal notaio (visure, contratti, documenti di identita').
INPUT_SOURCE: Final = "input_source"

# Allegato non sostanziale (accompagnatorio, non usato per generare la bozza).
ALLEGATO: Final = "allegato"

# Versione firmata dell'atto. Riservato: validazione separata.
ATTO_FIRMATO: Final = "atto_firmato"

# Bozza generata dal workflow (output del template engine).
DRAFT: Final = "draft"

# Letterali validi (per type-checking statico).
DocumentKind = Literal["input_source", "allegato", "atto_firmato", "draft"]

# Set comodo per filtri "tutti gli input".
INPUT_KINDS: Final = (INPUT_SOURCE, ALLEGATO)


__all__ = [
    "INPUT_SOURCE",
    "ALLEGATO",
    "ATTO_FIRMATO",
    "DRAFT",
    "INPUT_KINDS",
    "DocumentKind",
]
