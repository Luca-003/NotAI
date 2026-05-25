"""Classificatore zero-shot per chunk via embedding semantico.

Tier intermedio tra heuristic (microsecondi, miss alti) e LLM (8-20s).
Usa lo stesso modello di embedding gia' attivo (bge-m3 via Ollama o
equivalente): ~1-2s per chunk, riusa label embeddings cached.

Pipeline:
  1. Embed labels (una volta sola, in-memory cache LRU)
  2. Embed chunk text
  3. Cosine similarity vs ogni label
  4. Pick top se similarity >= MIN_SIM (default 0.55)
  5. Altrimenti: None -> fallback LLM

Vincolo zero-allucinazione: la classificazione NON inventa, sceglie tra
i Literal di ChunkClassification.document_type. Confidence = similarity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

# Soglia minima cosine per accettare la classificazione.
# Sotto -> incerto, fallback LLM.
MIN_SIMILARITY = 0.55

# Soglia confident (rationale chiarisce nel audit)
HIGH_CONFIDENCE = 0.70


# ---------------------------------------------------------------------------
# Label catalog: la descrizione e' RICCA (parole chiave del dominio) per
# aiutare l'embedding a matchare anche frasi specifiche del testo italiano
# notarile. NON e' il prompt LLM: e' solo il "concetto" che embeddiamo.
# ---------------------------------------------------------------------------

_LABELS: dict[str, str] = {
    "visura_catastale": (
        "visura catastale storica Agenzia delle Entrate Catasto Fabbricati. "
        "Identificativo immobile foglio particella subalterno categoria classe "
        "consistenza superficie rendita catastale. Intestazione titolare quota "
        "piena proprieta'. NCEU Nuovo Catasto Edilizio Urbano."
    ),
    "visura_ipotecaria": (
        "ispezione ipotecaria conservatoria registri immobiliari. Trascrizioni "
        "a favore e contro. Iscrizioni ipoteche pignoramenti sequestri. "
        "Conservatoria pubblicita' immobiliare. Servizio di pubblicita' immobiliare."
    ),
    "visura_camerale": (
        "visura camerale InfoCamere Telemaco Registro Imprese. Denominazione "
        "partita IVA forma giuridica data costituzione sede legale capitale "
        "sociale amministratori soci. Numero REA. Camera di Commercio."
    ),
    "atto_preliminare": (
        "proposta di acquisto contratto preliminare compravendita immobiliare. "
        "Promittente venditore promittente acquirente. Prezzo caparra confirmatoria. "
        "Termine per la stipula notarile. Prenotazione vendita appartamento immobile."
    ),
    "documento_identita": (
        "carta d'identita' passaporto patente di guida documento di riconoscimento. "
        "Comune di rilascio data di rilascio scadenza fotografia."
    ),
    "codice_fiscale": (
        "tessera codice fiscale Agenzia delle Entrate. Codice alfanumerico 16 "
        "caratteri. Tessera sanitaria."
    ),
    "perizia": (
        "perizia tecnica stima valutazione immobile valore di mercato. Perito "
        "asseverata giurata. Relazione tecnica."
    ),
    "certificato_anagrafico": (
        "certificato anagrafico ANPR stato di famiglia residenza cittadinanza. "
        "Comune ufficio anagrafe. Capofamiglia componenti famiglia anagrafica "
        "Ufficiale di Stato Civile."
    ),
    "altro": (
        "diffida ad adempiere atto di citazione ricorso decreto ingiuntivo "
        "statuto societario atto costitutivo fattura insoluta estratto conto "
        "certificato accordo separazione consensuale negoziazione assistita."
    ),
}


@dataclass(frozen=True)
class ZeroShotResult:
    document_type: str
    confidence: float
    rationale: str
    second_best: str  # secondo classificato (per audit/debug)
    second_score: float


# Cache module-scoped delle label embeddings (calcolate una volta).
_LABEL_EMB_CACHE: dict[str, list[float]] | None = None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _ensure_label_embeddings() -> dict[str, list[float]]:
    """Calcola (una volta sola) gli embedding per ogni label."""
    global _LABEL_EMB_CACHE
    if _LABEL_EMB_CACHE is not None:
        return _LABEL_EMB_CACHE
    # Import lazy per evitare ciclo
    from notai.contexts.ai.llm_gateway import embed_texts

    labels = list(_LABELS.keys())
    descs = [_LABELS[label] for label in labels]
    try:
        vectors = await embed_texts(descs)
    except Exception as e:  # noqa: BLE001
        logger.warning("notai.zero_shot.embed_labels_failed", error=str(e))
        return {}

    if not vectors or len(vectors) != len(labels):
        return {}

    cache = {label: vec for label, vec in zip(labels, vectors)}
    _LABEL_EMB_CACHE = cache
    return cache


async def classify_zero_shot(chunk_text: str) -> ZeroShotResult | None:
    """Classifica un chunk via cosine similarity con embedding pre-calcolati
    delle label descriptions. Ritorna None se nessuna label sopra MIN_SIMILARITY.
    """
    if not chunk_text or not chunk_text.strip():
        return None
    label_embs = await _ensure_label_embeddings()
    if not label_embs:
        return None

    from notai.contexts.ai.llm_gateway import embed_texts

    try:
        chunk_vectors = await embed_texts([chunk_text[:2000]])
    except Exception as e:  # noqa: BLE001
        logger.warning("notai.zero_shot.embed_chunk_failed", error=str(e))
        return None
    if not chunk_vectors:
        return None
    chunk_vec = chunk_vectors[0]

    # Scoring vs ogni label
    scores: list[tuple[str, float]] = []
    for label, label_vec in label_embs.items():
        scores.append((label, _cosine(chunk_vec, label_vec)))
    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores:
        return None

    top_label, top_score = scores[0]
    second_label = scores[1][0] if len(scores) > 1 else "—"
    second_score = scores[1][1] if len(scores) > 1 else 0.0

    if top_score < MIN_SIMILARITY:
        logger.debug(
            "notai.zero_shot.below_threshold",
            top_label=top_label,
            top_score=top_score,
            min=MIN_SIMILARITY,
        )
        return None

    # Margin check: se top ~ second, e' ambiguo -> meglio LLM
    margin = top_score - second_score
    if margin < 0.05 and top_score < HIGH_CONFIDENCE:
        return None

    rationale = (
        f"zero-shot: similarita' {top_score:.2f} > {MIN_SIMILARITY:.2f}, "
        f"margine vs '{second_label}' = {margin:.2f}"
    )
    return ZeroShotResult(
        document_type=top_label,
        confidence=min(top_score, 0.99),
        rationale=rationale,
        second_best=second_label,
        second_score=second_score,
    )


__all__ = ["classify_zero_shot", "ZeroShotResult", "MIN_SIMILARITY"]
