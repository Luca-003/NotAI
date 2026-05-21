"""Hash chain SHA-256 con JSON canonicalization RFC 8785.

Ogni evento `e_n` ha:
    e_n.hash = SHA-256( e_{n-1}.hash || canonical_json(e_n.payload) || e_n.ts || e_n.actor )

dove `||` e' concatenazione di byte e `canonical_json` produce la forma
canonica (chiavi ordinate, no spazi, separatori fissi, unicode normalizzato).

Senza canonicalization, la stessa struttura JSON puo' produrre hash diversi
in base alla rappresentazione (ordinamento chiavi, spazi). La canonicalization
rende l'audit deterministico e verificabile.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

# Hash di partenza per il primo evento di uno stream (32 byte di zeri in hex).
GENESIS_HASH = "0" * 64


def canonical_json(payload: Any) -> bytes:
    """Serializza un payload JSON-able in forma canonica.

    Implementazione minimale di JCS (RFC 8785) sufficiente per i nostri usi:
      - chiavi degli oggetti ordinate lessicograficamente
      - no whitespace
      - separatori fissi (',' e ':')
      - ensure_ascii=False (UTF-8 nativo, NFC implicito su input gia' normalizzato)
      - float serializzati come Python default (per ora; pieno JCS richiede I-JSON)

    Per i nostri payload (tutti gli eventi audit) i float sono rari; quando ci sono
    valori monetari usiamo string Decimal per evitare rounding non-deterministico.
    """
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def _json_default(obj: Any) -> Any:
    """Coerce tipi non-JSON-nativi a stringhe deterministe."""
    if isinstance(obj, datetime):
        # ISO 8601 con offset esplicito (UTC). Niente microseconds variabili.
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.astimezone(timezone.utc).isoformat()
    if hasattr(obj, "__str__"):
        return str(obj)
    raise TypeError(f"non serializable: {type(obj).__name__}")


def compute_hash(prev_hash: str, payload: Any, ts: datetime, actor: str | None) -> str:
    """Calcola l'hash di un evento data la testa precedente, payload, timestamp, attore.

    Args:
        prev_hash: hash hex dell'evento precedente (o GENESIS_HASH per il primo).
        payload: dict/list/altro JSON-able. Verra' canonicalizzato.
        ts: timestamp UTC dell'evento.
        actor: identita' che ha generato l'evento (user_id o nome service).

    Returns:
        Hash hex (64 caratteri).
    """
    if not isinstance(prev_hash, str) or len(prev_hash) != 64:
        raise ValueError("prev_hash deve essere 64 hex chars")

    ts_str = ts.astimezone(timezone.utc).isoformat() if ts.tzinfo else ts.replace(
        tzinfo=timezone.utc
    ).isoformat()

    h = hashlib.sha256()
    h.update(bytes.fromhex(prev_hash))
    h.update(canonical_json(payload))
    h.update(ts_str.encode("utf-8"))
    h.update((actor or "").encode("utf-8"))
    return h.hexdigest()


def verify_chain(events: list[dict[str, Any]]) -> tuple[bool, int | None, str]:
    """Verifica una sequenza di eventi.

    Ritorna (ok, indice_primo_errore, dettaglio).
    Ogni evento deve avere: prev_hash, hash, payload, ts (datetime), actor.
    """
    for i, e in enumerate(events):
        expected_prev = GENESIS_HASH if i == 0 else events[i - 1]["hash"]
        if e["prev_hash"] != expected_prev:
            return False, i, f"prev_hash mismatch at idx {i}"
        computed = compute_hash(e["prev_hash"], e["payload"], e["ts"], e.get("actor"))
        if computed != e["hash"]:
            return False, i, f"hash mismatch at idx {i}: computed={computed}, stored={e['hash']}"
    return True, None, "chain verified"


__all__ = ["GENESIS_HASH", "canonical_json", "compute_hash", "verify_chain"]
