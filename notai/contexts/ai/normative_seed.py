"""Seed normativa: insieme minimo di articoli CC + DPR 131/86 per demo.

Testo NON normativo ufficiale (e' una parafrasi sintetica per evitare problemi
di copyright sul Codice). In Fase 5+ verra' sostituito da ingestion automatica
da Normattiva.

Eseguibile via:
    python -m notai.contexts.ai.normative_seed
"""

from __future__ import annotations

import asyncio

import structlog

from notai.contexts.ai.rag import IngestItem, ingest

logger = structlog.get_logger(__name__)


SEED_ITEMS: list[IngestItem] = [
    IngestItem(
        citation="art. 1325 c.c.",
        text=(
            "Requisiti del contratto. I requisiti essenziali del contratto sono: "
            "1) l'accordo delle parti; 2) la causa; 3) l'oggetto; 4) la forma, "
            "quando risulta che e' prescritta dalla legge sotto pena di nullita'."
        ),
    ),
    IngestItem(
        citation="art. 1350 c.c.",
        text=(
            "Atti che devono farsi per iscritto. Devono farsi per atto pubblico o "
            "per scrittura privata, sotto pena di nullita': i contratti che "
            "trasferiscono la proprieta' di beni immobili; quelli che costituiscono, "
            "modificano o trasferiscono il diritto di usufrutto, di superficie, di "
            "enfiteusi su beni immobili."
        ),
    ),
    IngestItem(
        citation="art. 1470 c.c.",
        text=(
            "Nozione di vendita. La vendita e' il contratto che ha per oggetto il "
            "trasferimento della proprieta' di una cosa o il trasferimento di un "
            "altro diritto verso il corrispettivo di un prezzo."
        ),
    ),
    IngestItem(
        citation="art. 1490 c.c.",
        text=(
            "Garanzia per i vizi della cosa venduta. Il venditore e' tenuto a "
            "garantire che la cosa venduta sia immune da vizi che la rendano "
            "inidonea all'uso a cui e' destinata o ne diminuiscano in modo "
            "apprezzabile il valore. Il patto con cui si esclude o si limita la "
            "garanzia non ha effetto, se il venditore ha in mala fede taciuto al "
            "compratore i vizi della cosa."
        ),
    ),
    IngestItem(
        citation="art. 2643 c.c.",
        text=(
            "Atti soggetti a trascrizione. Si devono rendere pubblici col mezzo della "
            "trascrizione: 1) i contratti che trasferiscono la proprieta' di beni "
            "immobili; 2) i contratti che costituiscono, trasferiscono o modificano "
            "il diritto di usufrutto su beni immobili, il diritto di superficie, i "
            "diritti del concedente e dell'enfiteuta."
        ),
    ),
    IngestItem(
        citation="art. 2644 c.c.",
        text=(
            "Effetti della trascrizione. Gli atti enunciati nell'articolo precedente "
            "non hanno effetto riguardo ai terzi che a qualunque titolo hanno "
            "acquistato diritti sugli immobili in base a un atto trascritto o "
            "iscritto anteriormente alla trascrizione degli atti medesimi."
        ),
    ),
    IngestItem(
        citation="art. 2697 c.c.",
        text=(
            "Onere della prova. Chi vuol far valere un diritto in giudizio deve "
            "provare i fatti che ne costituiscono il fondamento. Chi eccepisce "
            "l'inefficacia di tali fatti ovvero eccepisce che il diritto si e' "
            "modificato o estinto deve provare i fatti su cui l'eccezione si fonda."
        ),
    ),
    IngestItem(
        citation="DPR 131/86 art. 1",
        text=(
            "L'imposta di registro si applica, nella misura indicata nella tariffa "
            "allegata al presente testo unico, agli atti soggetti a registrazione e "
            "a quelli volontariamente presentati per la registrazione."
        ),
    ),
    IngestItem(
        citation="DPR 131/86 tariffa parte I art. 1",
        text=(
            "Atti traslativi a titolo oneroso della proprieta' di beni immobili in "
            "genere: aliquota del 9 per cento, salve le agevolazioni prima casa."
        ),
    ),
    IngestItem(
        citation="DPR 131/86 tariffa parte I art. 1 nota II-bis",
        text=(
            "Atti traslativi a titolo oneroso della proprieta' di abitazioni non "
            "di lusso, in presenza dei requisiti di legge per la prima casa: "
            "aliquota del 2 per cento."
        ),
    ),
]


async def main() -> int:
    n = await ingest(SEED_ITEMS)
    logger.info("notai.normative_seed.completed", ingested=n)
    print(f"seeded {n} normative items")
    return n


if __name__ == "__main__":
    asyncio.run(main())
