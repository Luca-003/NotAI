"""Module registry - manifest statico dei moduli del sistema.

I moduli rappresentano "capacita' funzionali" attivabili/disattivabili per tenant.
Il manifest e' STATICO (definito in codice, non in DB): aggiungere/rimuovere un
modulo richiede un PR. Solo lo stato attivo/disattivo e' dinamico (DB-persisted).

Categorie:
  - core.*        : sempre attivi, non disattivabili (essenziali al funzionamento)
  - notaio.*      : capacita' del vertical notarile
  - legale.*      : capacita' del vertical avvocato
  - ai.*          : moduli AI (richiedono Ollama o LLM equivalente)
  - integrations.*: adapter verso portali esterni
  - audit.*       : capacita' di audit e conservazione
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Module:
    """Definizione statica di una capacita' funzionale."""

    id: str                         # es. "ai.classify_clause"
    name: str                       # nome leggibile in UI
    category: str                   # core | notaio | legale | ai | integrations | audit
    description: str
    # Dipendenze "soft": se manca un modulo richiesto, l'UI mostra warning
    # ma il modulo puo' essere attivato lo stesso (l'enforcement runtime
    # bloccchera' le call effettive).
    requires: tuple[str, ...] = field(default_factory=tuple)
    # Moduli non disattivabili (sempre on). I core.* sono sempre essential=True.
    essential: bool = False
    # Default: attivo all'enrollment di un nuovo tenant
    default_enabled: bool = True
    # Etichette opzionali per filtri in UI (es. "beta", "experimental", "ai-act-high-risk")
    tags: tuple[str, ...] = field(default_factory=tuple)


# -----------------------------------------------------------------------------
# Manifest - in ordine logico (categoria, poi nome)
# -----------------------------------------------------------------------------

MODULES: tuple[Module, ...] = (
    # Core (sempre attivi)
    Module(
        id="core.iam",
        name="Identita' e accessi",
        category="core",
        description="Tenant, utenti, ruoli, JWT, RLS multi-tenant.",
        essential=True,
    ),
    Module(
        id="core.audit",
        name="Audit forense",
        category="core",
        description="Catena hash SHA-256 append-only su ogni evento + timestamp RFC 3161.",
        essential=True,
    ),
    Module(
        id="core.practices",
        name="Fascicoli / Pratiche",
        category="core",
        description="Gestione del fascicolo (Practice) come aggregate root.",
        essential=True,
    ),
    Module(
        id="core.acts",
        name="Atti",
        category="core",
        description="Atti notarili/legali collegati alle pratiche.",
        essential=True,
    ),
    Module(
        id="core.parties",
        name="Parti (anagrafiche)",
        category="core",
        description="Anagrafiche persone fisiche e giuridiche, ruoli negli atti.",
        essential=True,
    ),
    Module(
        id="core.documents",
        name="Documenti",
        category="core",
        description="Storage documenti su MinIO con WORM e firma.",
        essential=True,
    ),

    # Notaio vertical
    Module(
        id="notaio.workflow",
        name="Workflow atto notarile",
        category="notaio",
        description="Ciclo di vita atto: visure -> bozza -> imposte -> review -> firma.",
        requires=("core.acts", "core.practices"),
    ),
    Module(
        id="notaio.tax_calculator",
        name="Calcolo imposte",
        category="notaio",
        description="Registro, ipotecaria, catastale (DPR 131/86, D.Lgs 347/90).",
        requires=("notaio.workflow",),
    ),
    Module(
        id="notaio.repertorio",
        name="Repertorio notarile",
        category="notaio",
        description="Numerazione progressiva, indice annuale, deposito mensile.",
        requires=("core.acts",),
        default_enabled=False,
        tags=("planned",),
    ),
    Module(
        id="notaio.aml",
        name="Antiriciclaggio (D.Lgs 231/2007)",
        category="notaio",
        description="CDD, AUI, conservazione 10 anni, SOS a UIF.",
        requires=("core.parties",),
        default_enabled=False,
        tags=("planned",),
    ),

    # Legale vertical
    Module(
        id="legale.fascicolo",
        name="Fascicolo legale",
        category="legale",
        description="Fascicoli civili/penali, controparti, materia, stato.",
        requires=("core.practices",),
        default_enabled=False,
        tags=("planned",),
    ),
    Module(
        id="legale.scadenzario",
        name="Scadenzario processuale",
        category="legale",
        description="Scadenze CPC/CPP con calcolo termini, sospensione feriale.",
        requires=("legale.fascicolo",),
        default_enabled=False,
        tags=("planned",),
    ),
    Module(
        id="legale.pct",
        name="PCT - Processo Civile Telematico",
        category="legale",
        description="Deposito atti telematici, busta crittografica.",
        requires=("legale.fascicolo",),
        default_enabled=False,
        tags=("planned",),
    ),
    Module(
        id="legale.onorari_dm55",
        name="Calcolo onorari (DM 55/2014)",
        category="legale",
        description="Tabelle per valore/fase/grado, CPA 4%, IVA, ritenuta.",
        requires=("legale.fascicolo",),
        default_enabled=False,
        tags=("planned",),
    ),

    # AI
    Module(
        id="ai.rag",
        name="RAG normativa locale",
        category="ai",
        description="Knowledge base Qdrant + embeddings locali (bge-m3).",
        requires=("core.audit",),
        tags=("ai-act",),
    ),
    Module(
        id="ai.classify_clause",
        name="Classificazione clausole",
        category="ai",
        description="Tagging semantico e suggerimento normativo con grounding.",
        requires=("ai.rag",),
        tags=("ai-act",),
    ),
    Module(
        id="ai.draft_suggestion",
        name="Suggerimento redrafting",
        category="ai",
        description="Riformulazione clausole con citation obbligatoria.",
        requires=("ai.rag",),
        tags=("ai-act", "ai-act-high-risk"),
    ),
    Module(
        id="ai.abstention_detector",
        name="Abstention detector (zero-allucinazione)",
        category="ai",
        description="Gate obbligatorio: blocca output AI non grounded.",
        requires=("ai.rag",),
        essential=False,  # disattivabile SOLO per debug; in prod sempre on
        tags=("ai-act", "critical"),
    ),

    # Integrazioni esterne
    Module(
        id="integrations.telemaco",
        name="InfoCamere / Telemaco",
        category="integrations",
        description="Visure camerali, deposito bilanci, beneficiario effettivo.",
        requires=("core.parties",),
    ),
    Module(
        id="integrations.anpr",
        name="ANPR (Anagrafe Nazionale)",
        category="integrations",
        description="Verifica anagrafica, codice fiscale.",
        requires=("core.parties",),
    ),
    Module(
        id="integrations.catasto",
        name="Catasto / SISTER",
        category="integrations",
        description="Visure catastali, planimetrie, dati identificativi.",
        requires=("notaio.workflow",),
        default_enabled=False,
        tags=("planned",),
    ),
    Module(
        id="integrations.conservatoria",
        name="Conservatoria Registri Immobiliari",
        category="integrations",
        description="Ispezioni ipotecarie, trascrizioni.",
        requires=("notaio.workflow",),
        default_enabled=False,
        tags=("planned",),
    ),
    Module(
        id="integrations.entrate_adempimento_unico",
        name="Agenzia Entrate - Adempimento Unico",
        category="integrations",
        description="Registrazione + trascrizione + voltura telematica.",
        requires=("notaio.workflow",),
        default_enabled=False,
        tags=("planned",),
    ),
    Module(
        id="integrations.pra",
        name="PRA - Pubblico Registro Automobilistico",
        category="integrations",
        description="Visure veicoli, passaggi di proprieta'.",
        requires=("core.acts",),
        default_enabled=False,
        tags=("planned",),
    ),
    Module(
        id="integrations.sdi",
        name="SdI - Fatturazione elettronica",
        category="integrations",
        description="Invio fatture clienti via Sistema di Interscambio.",
        default_enabled=False,
        tags=("planned",),
    ),

    # Audit / Conservazione
    Module(
        id="audit.export",
        name="Export bundle probatorio",
        category="audit",
        description="Export firmato di una catena audit per esibizione probatoria.",
        requires=("core.audit",),
    ),
    Module(
        id="audit.agid_conservation",
        name="Conservazione a norma AgID",
        category="audit",
        description="Versamento in conservazione decennale via conservatore accreditato.",
        requires=("core.documents",),
        default_enabled=False,
        tags=("planned",),
    ),
)


# -----------------------------------------------------------------------------
# API di lookup
# -----------------------------------------------------------------------------


_MODULES_BY_ID: dict[str, Module] = {m.id: m for m in MODULES}


def get_module(module_id: str) -> Module | None:
    return _MODULES_BY_ID.get(module_id)


def all_modules() -> Iterable[Module]:
    return MODULES


def essential_module_ids() -> set[str]:
    return {m.id for m in MODULES if m.essential}


def default_enabled_module_ids() -> set[str]:
    return {m.id for m in MODULES if m.default_enabled or m.essential}


__all__ = [
    "MODULES",
    "Module",
    "all_modules",
    "default_enabled_module_ids",
    "essential_module_ids",
    "get_module",
]
