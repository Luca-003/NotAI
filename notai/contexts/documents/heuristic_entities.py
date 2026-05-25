"""Entity extractor euristico per i chunk.

Regex domain-specific per estrarre:
  - person_name (cognome NOME pattern italiani)
  - fiscal_code (CF 16 char)
  - vat_number (P.IVA 11 cifre)
  - immobile_cadastral (foglio/particella/subalterno)
  - amount (importi EUR)
  - date (formato IT)
  - address (Via X N civico)
  - iban

Confidence:
  - 1.00 per pattern strict (CF 16-char, P.IVA 11-cifre, IBAN, codice catastale)
  - 0.90 per pattern loose (date, importi)
  - 0.85 per address e person_name (piu' rumorosi)

Vincolo zero-allucinazione: tutte le entity hanno il `value` letteralmente
presente nel testo (regex non genera, estrae).
"""

from __future__ import annotations

import re
from typing import Iterable

from notai.contexts.ai.schemas import ExtractedEntity


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# CF italiano: 6 lettere + 2 cifre + 1 lettera + 2 cifre + 1 lettera + 3 cifre + 1 lettera
_CF_RE = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")

# P.IVA italiana: 11 cifre. Word boundary per evitare 11+ cifre consecutivi.
_PIVA_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")

# IBAN IT: IT + 2 cifre + 22 alfanumerici (totale 27 char)
_IBAN_RE = re.compile(r"\bIT\d{2}[A-Z]{1}\d{5}\d{5}[A-Z0-9]{12}\b")

# Catasto: foglio + particella + (subalterno opzionale)
# Forme accettate:
#   "Foglio 425 Particella 87 Sub 12"
#   "foglio: 425, particella 87, sub. 12"
_CATASTO_RE = re.compile(
    r"foglio\s*N?\.?\s*:?\s*(\d{1,5})"
    r".{0,40}?"
    r"particella\s*N?\.?\s*:?\s*(\d{1,5})"
    r"(?:.{0,40}?(?:sub(?:alterno)?)\s*N?\.?\s*:?\s*(\d{1,5}))?",
    re.I | re.DOTALL,
)

# Categoria catastale: A/1, A/2, ..., C/6, ecc.
_CAT_CATASTALE_RE = re.compile(r"\b[A-C]/\d{1,2}\b")

# Importi EUR. Formato italiano: 285.000,00 EUR / EUR 285.000,00 / 285000 €
_IMPORT_RE = re.compile(
    r"(?:EUR|€)\s*([\d]{1,3}(?:[.\s]\d{3})*(?:,\d{2})?|[\d]+(?:[.,]\d{2})?)"
    r"|"
    r"([\d]{1,3}(?:[.\s]\d{3})*(?:,\d{2})?|[\d]+(?:[.,]\d{2})?)\s*(?:EUR|€)",
    re.I,
)

# Date italiane: 12/03/2010, 12-03-2010, 12.03.2010, 12 marzo 2010
_MESI = (
    "gennaio|febbraio|marzo|aprile|maggio|giugno|"
    "luglio|agosto|settembre|ottobre|novembre|dicembre"
)
_DATE_NUM_RE = re.compile(r"\b(0?[1-9]|[12]\d|3[01])[/.\-](0?[1-9]|1[0-2])[/.\-](\d{2,4})\b")
_DATE_TEXT_RE = re.compile(
    rf"\b(0?[1-9]|[12]\d|3[01])\s+({_MESI})\s+(\d{{4}})\b",
    re.I,
)

# Indirizzi italiani: Via/Viale/Corso/Piazza X NUMERO
_ADDRESS_RE = re.compile(
    r"\b(?:Via|Viale|V\.le|Vle\.|Corso|C\.so|Piazza|P\.zza|Largo|Vicolo)\s+"
    r"(?:dei?\s+|degli\s+|delle\s+|della\s+|del\s+|di\s+)?"
    r"[A-Z][\w'À-ſ]+(?:\s+[A-Z][\w'À-ſ]+){0,3}"
    r"\s*,?\s*\d{1,4}\b",
)

# Persona: CF + nome scritto vicino. Cerco "COGNOME Nome" o "COGNOME NOME" in MAIUSCOLO.
# Es. "ROSSI MARIO" o "MARIO ROSSI"
_PERSON_RE = re.compile(
    r"\b([A-ZÀ-ſ]{3,15})\s+([A-ZÀ-ſ]{3,15})\b"
)

# Denominazione societaria
_COMPANY_RE = re.compile(
    r"\b([A-Z][\w'À-ſ&\-]+(?:\s+[A-Z][\w'À-ſ&\-]+){0,3})"
    r"\s+(?:S\.?R\.?L\.?|S\.?P\.?A\.?|S\.?N\.?C\.?|S\.?A\.?S\.?)\b",
)


def _add(out: list[ExtractedEntity], kind: str, value: str, conf: float, seen: set[tuple[str, str]]) -> None:
    """Append senza duplicati."""
    v = value.strip()
    if not v:
        return
    key = (kind, v.lower())
    if key in seen:
        return
    seen.add(key)
    try:
        out.append(ExtractedEntity(type=kind, value=v[:512], confidence=conf))  # type: ignore[arg-type]
    except Exception:
        # value troppo lungo o type non valido: ignora
        pass


def extract_entities(text: str) -> list[ExtractedEntity]:
    """Estrae entita' dal chunk text via regex. Output ordinato per appearance.

    Limite hard: max 30 entita' per chunk (oltre = rumore).
    """
    if not text:
        return []
    out: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()

    for m in _CF_RE.finditer(text):
        _add(out, "fiscal_code", m.group(0), 1.0, seen)

    for m in _PIVA_RE.finditer(text):
        # Filtra le P.IVA "false" (es. numero di pagina, CAP) usando context.
        # Una P.IVA vera di solito ha "P.IVA"/"VAT"/"partita iva" prima.
        start = max(0, m.start() - 40)
        ctx = text[start:m.start()].lower()
        if any(kw in ctx for kw in ("p.iva", "partita iva", "vat", "p iva", "piva")):
            _add(out, "vat_number", m.group(0), 1.0, seen)
        # Senza contesto: skip (ambiguo)

    for m in _IBAN_RE.finditer(text):
        _add(out, "iban", m.group(0), 1.0, seen)

    for m in _CATASTO_RE.finditer(text):
        foglio = m.group(1)
        particella = m.group(2)
        sub = m.group(3) or ""
        # immobile_cadastral come un valore composto leggibile
        if sub:
            v = f"foglio {foglio}, particella {particella}, sub {sub}"
        else:
            v = f"foglio {foglio}, particella {particella}"
        _add(out, "immobile_cadastral", v, 1.0, seen)

    for m in _CAT_CATASTALE_RE.finditer(text):
        _add(out, "other", f"categoria_catastale={m.group(0)}", 0.9, seen)

    for m in _IMPORT_RE.finditer(text):
        v = (m.group(1) or m.group(2) or "").strip()
        if not v:
            continue
        # Solo importi con almeno 3 cifre (evita "5 EUR", "10 €" che spesso sono rumore)
        digits = sum(1 for c in v if c.isdigit())
        if digits < 3:
            continue
        _add(out, "amount", f"EUR {v}", 0.9, seen)

    for m in _DATE_NUM_RE.finditer(text):
        _add(out, "date", m.group(0), 0.9, seen)

    for m in _DATE_TEXT_RE.finditer(text):
        _add(out, "date", m.group(0), 0.9, seen)

    for m in _ADDRESS_RE.finditer(text):
        _add(out, "address", m.group(0), 0.85, seen)

    for m in _COMPANY_RE.finditer(text):
        _add(out, "company_name", m.group(0), 0.9, seen)

    # Persone: piu' rumorose, le metto per ultime e cappiamo a 5
    person_count = 0
    for m in _PERSON_RE.finditer(text):
        cog, nome = m.group(1), m.group(2)
        full = f"{cog} {nome}"
        # Skip se sembra titolo (VIA ROMA, CORSO ITALIA -> 2 maiuscole non e' persona)
        if cog in {"VIA", "CORSO", "VIALE", "PIAZZA", "LARGO", "VICOLO", "CAP", "CF", "EUR"}:
            continue
        if nome in {"SRL", "SPA", "SNC", "SAS", "CC", "CPC", "DPR", "DLGS"}:
            continue
        _add(out, "person_name", full, 0.85, seen)
        person_count += 1
        if person_count >= 5:
            break

    return out[:30]


__all__ = ["extract_entities"]
