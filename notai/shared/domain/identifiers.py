"""Helper per parsing tollerante di identificatori (UUID stringhe, ecc.)."""

from __future__ import annotations

import uuid


def as_uuid_or_none(s: str | None) -> uuid.UUID | None:
    """Converte `s` in UUID se valido, altrimenti None.

    Usato per campi come `actor`/`user_id` che possono essere:
      - una stringa UUID legittima (es. da JWT 'sub')
      - una stringa di sistema ("ingestion-worker", "demo-user")
      - None

    Il check `len == 36` di prima era fragile: 36 char non implicano un UUID valido.
    Qui validiamo davvero parsing UUID e accettiamo solo quello.
    """
    if not s:
        return None
    try:
        return uuid.UUID(s)
    except (ValueError, AttributeError, TypeError):
        return None
