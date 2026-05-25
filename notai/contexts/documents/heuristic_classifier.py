"""Classificatore euristico per Document.kind / Chunk document_type.

Pre-pass CPU prima del LLM: per i casi OVVI (filename + header pattern)
emette una classificazione confident SENZA chiamare LLM.

Trade-off:
  - Velocita': microsecondi vs 8-20s (LLM 3B)
  - Qualita': nessuna entity_type extraction (slot_extractor poi lavora
    direttamente sul testo del chunk - non perde nulla)
  - Falsi positivi: limitati alle regole hardcoded (visure, fatture, atti
    giudiziari, statuti). Cose ambigue cadono sul LLM.

Filosofia: meglio "non confident" e chiamare LLM, che "confident wrong"
(zero-allucinazione si applica anche qui: vincolo di sicurezza).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CONFIDENCE_THRESHOLD = 0.80


@dataclass(frozen=True)
class HeuristicResult:
    """Risultato del pre-classificatore."""

    document_type: Literal[
        "visura_catastale",
        "visura_camerale",
        "visura_ipotecaria",
        "atto_preliminare",
        "documento_identita",
        "codice_fiscale",
        "perizia",
        "certificato_anagrafico",
        "altro",
        "indeterminato",
    ]
    confidence: float
    rationale: str  # quale rule e' scattata (per audit/debug)
    suggested_tags: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Rules: tuple (priority, regex_pattern, document_type, confidence, tags)
# Priority piu' basso = applicato prima. Prima match vince.
# ---------------------------------------------------------------------------


# 1) Filename rules - hint molto forte se l'utente nomina i file ovvi
_FILENAME_RULES: tuple[tuple[re.Pattern, str, float], ...] = (
    (re.compile(r"visura.{0,3}catastal", re.I), "visura_catastale", 0.95),
    (re.compile(r"visura.{0,3}ipo.{0,3}catastal", re.I), "visura_ipotecaria", 0.95),
    (re.compile(r"visura.{0,3}ipotecari", re.I), "visura_ipotecaria", 0.95),
    (re.compile(r"visura.{0,3}cameral", re.I), "visura_camerale", 0.95),
    (re.compile(r"telemaco", re.I), "visura_camerale", 0.92),
    (re.compile(r"anpr|anagrafic", re.I), "certificato_anagrafico", 0.90),
    (re.compile(r"stato.{0,3}famigli", re.I), "certificato_anagrafico", 0.90),
    (re.compile(r"contratto|preliminare|proposta.{0,3}acquist", re.I), "atto_preliminare", 0.85),
    (re.compile(r"diffida", re.I), "altro", 0.75),
    (re.compile(r"fattur", re.I), "altro", 0.75),
)


# 2) Content-header rules: prime 500 char del testo
#    Pattern molto specifici per evitare falsi positivi
_HEADER_RULES: tuple[tuple[re.Pattern, str, float, str], ...] = (
    (
        re.compile(
            r"VISURA\s+CATASTALE|N\.?C\.?E\.?U|catasto\s+fabbricati|"
            r"foglio\s*\d+.{0,30}particella\s*\d+",
            re.I,
        ),
        "visura_catastale",
        0.90,
        "match header NCEU/foglio/particella",
    ),
    (
        re.compile(
            r"ispezione\s+ipotecaria|servizi\s+di\s+pubblicita.{0,5}immobiliare|"
            r"trascrizioni?\s+a\s+favore",
            re.I,
        ),
        "visura_ipotecaria",
        0.90,
        "match header ispezione ipotecaria",
    ),
    (
        re.compile(r"registro\s+imprese|InfoCamere|REA\s+nr?\.|partita\s+iva", re.I),
        "visura_camerale",
        0.85,
        "match header registro imprese",
    ),
    (
        re.compile(r"proposta\s+di\s+acquisto|preliminare\s+di\s+(vendita|compravendita)", re.I),
        "atto_preliminare",
        0.88,
        "match header proposta/preliminare",
    ),
    (
        re.compile(r"^(\s|\W)*ATTO\s+DI\s+CITAZIONE\b", re.I | re.MULTILINE),
        "altro",  # non c'e' tipo specifico per atto citazione in Literal corrente
        0.85,
        "match header atto di citazione (legale)",
    ),
    (
        re.compile(
            r"RICORSO\s+PER\s+DECRETO\s+INGIUNTIVO|art\.\s*633\s+c\.?p\.?c\.?",
            re.I,
        ),
        "altro",
        0.85,
        "match header decreto ingiuntivo",
    ),
    (
        re.compile(r"STATUTO\s+SOCIALE|ACT(O|TO)\s+COSTITUTIVO", re.I),
        "altro",
        0.80,
        "match header statuto/atto costitutivo SRL",
    ),
)


# 3) Tag estrazioni veloci (case-insensitive ma uno o due match)
_TAG_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bMilano\b|\b20[0-9]{3}\b\s+Milano", re.I), "milano"),
    (re.compile(r"\bRoma\b|\b001[0-9]{2}\b\s+Roma", re.I), "roma"),
    (re.compile(r"\bTorino\b", re.I), "torino"),
    (re.compile(r"\bNapoli\b", re.I), "napoli"),
    (re.compile(r"\bprima\s+casa\b", re.I), "prima-casa"),
    (re.compile(r"\bcompravendita\b", re.I), "compravendita"),
    (re.compile(r"\bdonazion[ei]\b", re.I), "donazione"),
    (re.compile(r"\bSRL\b|societ.{1,3}\s+a\s+responsabilit", re.I), "srl"),
    (re.compile(r"\bvenditor[ei]\b", re.I), "venditore"),
    (re.compile(r"\bacquirent[ei]\b", re.I), "acquirente"),
    (re.compile(r"\bimmobil[ei]\b", re.I), "immobile"),
)


def _extract_tags(text: str) -> tuple[str, ...]:
    """Estrae tag obvii dal testo (case-insensitive, dedup)."""
    found: list[str] = []
    seen: set[str] = set()
    for pat, tag in _TAG_PATTERNS:
        if tag in seen:
            continue
        if pat.search(text):
            found.append(tag)
            seen.add(tag)
    return tuple(found)


def classify_heuristic(filename: str | None, text: str) -> HeuristicResult | None:
    """Tenta classificazione euristica. Ritorna None se nessuna rule e'
    confident abbastanza (sotto soglia 0.80 -> fallback LLM).

    Args:
        filename: nome del file sorgente (es. "visura-catastale.md")
        text: testo del chunk (analizziamo solo i primi 500 char)

    Returns:
        HeuristicResult o None se nessuna regola matcha confident.
    """
    fname = (filename or "").strip()
    snippet = (text or "")[:500]
    tags = _extract_tags(snippet)

    # 1) Filename match (preferito: piu' affidabile dei contenuti per i demo)
    if fname:
        for pat, doc_type, conf in _FILENAME_RULES:
            if pat.search(fname):
                if conf >= CONFIDENCE_THRESHOLD:
                    return HeuristicResult(
                        document_type=doc_type,  # type: ignore[arg-type]
                        confidence=conf,
                        rationale=f"filename match: {pat.pattern[:40]}",
                        suggested_tags=tags,
                    )

    # 2) Content-header match
    for pat, doc_type, conf, why in _HEADER_RULES:
        if pat.search(snippet):
            if conf >= CONFIDENCE_THRESHOLD:
                return HeuristicResult(
                    document_type=doc_type,  # type: ignore[arg-type]
                    confidence=conf,
                    rationale=why,
                    suggested_tags=tags,
                )

    return None


__all__ = ["HeuristicResult", "classify_heuristic", "CONFIDENCE_THRESHOLD"]
