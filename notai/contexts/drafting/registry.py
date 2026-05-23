"""Act Template Registry - carica i template di atto da filesystem.

I template definiscono la struttura di un atto (notarile o legale): sezioni,
relies_on per la provenance, requirement degli slot di input. Caricati a startup
da file YAML in `notai/templates/`. In Fase 5+ verranno caricati anche da DB
(tabella act_templates) per permettere agli admin di aggiungere template a
runtime via UI senza redeploy.

Convenzione id: `<categoria>.<sottotipo>.<variante>:v<N>`
  - notarile.compravendita.immobiliare:v1
  - legale.civile.atto_citazione:v1
  - legale.civile.decreto_ingiuntivo:v1
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


@dataclass(frozen=True)
class SectionSpec:
    """Specifica di una sezione del documento di output."""

    id: str
    title: str
    text_template: str          # markdown con placeholder {nome_slot}
    relies_on: tuple[str, ...]  # entity_types che alimentano la provenance


@dataclass(frozen=True)
class ActTemplate:
    """Definizione completa di un template di atto."""

    id: str
    name: str
    category: str               # "notarile" | "legale" | "misto"
    subcategory: str | None     # es. "civile", "compravendita", ...
    description: str
    requires_modules: tuple[str, ...]
    slot_schema: dict[str, Any]  # JSON schema-like: campi richiesti
    # Step opzionali del workflow (se omesso, default: visure + draft + tax + review)
    workflow_skip_steps: tuple[str, ...]
    sections: tuple[SectionSpec, ...]
    tags: tuple[str, ...]

    def render_sections(self, slots: dict[str, Any]) -> list[dict[str, Any]]:
        """Sostituisce i placeholder negli `text_template` con i valori dagli slot.

        Placeholder: `{key}` -> str(slots.get('key', '—')). Niente Jinja per ora
        (zero-allucinazione: no esecuzione di codice nei template). Per format
        complessi (es. lista parti) i template hanno gia' il markdown statico
        e i campi vengono iniettati come stringhe semplici.
        """
        out: list[dict[str, Any]] = []
        for s in self.sections:
            try:
                text = s.text_template.format(**_safe_slots(slots))
            except (KeyError, IndexError) as e:
                logger.warning(
                    "notai.template.placeholder_missing",
                    template_id=self.id,
                    section_id=s.id,
                    error=str(e),
                )
                text = s.text_template
            out.append({
                "id": s.id,
                "title": s.title,
                "text": text,
                "relies_on": list(s.relies_on),
            })
        return out


def _safe_slots(slots: dict[str, Any]) -> dict[str, Any]:
    """Wrapper di slots che fa default a '—' per chiavi mancanti.

    Usa una dict subclass per evitare KeyError nel format.
    """

    class _SafeDict(dict):  # type: ignore[type-arg]
        def __missing__(self, key: str) -> str:  # noqa: D401
            return "—"

    # Sostituiamo dict semplice con quello sicuro; precomputiamo alcuni helper
    base = _SafeDict(slots)
    # Aggiungiamo `parties_md` formattato (sostituisce la lista raw)
    parties = slots.get("parties") or []
    base["parties_md"] = (
        "\n".join(
            f"- **{p.get('role', '-')}** (`{p.get('kind', '-')}`): "
            f"CF/PIVA `{p.get('fiscal_code') or p.get('vat') or '—'}`"
            for p in parties
        )
        or "_(nessuna parte indicata)_"
    )
    # base_imponibile formattato
    bi = slots.get("base_imponibile")
    base["base_imponibile_fmt"] = (
        f"{bi:,.2f}".replace(",", ".") if isinstance(bi, (int, float)) else "—"
    )
    # Visure summary inline
    visure = slots.get("visure_summaries") or []
    base["visure_md"] = (
        "\n".join(
            f"- **{v.get('source')}** — {v.get('summary') or '(dati non disponibili)'} "
            f"`hash: {(v.get('hash') or '')[:12]}…`"
            for v in visure
        )
        or "_(nessuna visura)_"
    )

    # Numerici opzionali: rendita catastale (EUR)
    rc = slots.get("immobile_rendita")
    base["immobile_rendita_fmt"] = (
        f"{float(rc):,.2f}".replace(",", ".") if rc not in (None, "", "—") else "—"
    )

    # Prezzo in lettere (semplice). In Fase 5 conversione completa via libreria.
    base["base_imponibile_lettere"] = "(prezzo da scrivere in lettere)"

    # Blocco prima casa
    base["prima_casa_block"] = (
        (
            "L'acquirente, ai sensi della nota II-bis dell'art. 1 Tariffa parte I "
            "DPR 131/86, **DICHIARA** di voler usufruire delle agevolazioni "
            "'prima casa': impegno a trasferire la residenza nel Comune entro 18 "
            "mesi; non titolarita' di altra abitazione nello stesso Comune ne' "
            "di altra prima casa nel territorio nazionale."
        )
        if slots.get("is_prima_casa")
        else "Acquisto a regime ordinario (no agevolazione prima casa)."
    )

    # Data di oggi spezzata in giorno/mese/anno italiano (per intestazione atto)
    from datetime import datetime as _dt
    _now = _dt.now()
    _mesi = [
        "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    ]
    base["today_giorno"] = str(_now.day)
    base["today_mese"] = _mesi[_now.month - 1]
    base["today_anno"] = str(_now.year)
    base.setdefault("luogo_stipula_o_default", "(luogo della stipula)")

    # Sommario slot estratti vs astenuti (note_tecniche)
    extracted_slots = slots.get("_extracted_slot_names") or []
    abstained_slots = slots.get("_abstained_slot_names") or []
    summary_lines = []
    if extracted_slots:
        summary_lines.append(f"  - estratti dai documenti: {', '.join(extracted_slots)}")
    if abstained_slots:
        summary_lines.append(f"  - non estratti (da completare a mano): {', '.join(abstained_slots)}")
    if not summary_lines:
        summary_lines.append("  - (nessuno slot estratto da documenti)")
    base["slots_summary_md"] = "\n".join(summary_lines)

    return base


def _parse_template(data: dict, source_file: str) -> ActTemplate:
    sections = tuple(
        SectionSpec(
            id=s["id"],
            title=s["title"],
            text_template=s["text"],
            relies_on=tuple(s.get("relies_on") or []),
        )
        for s in data.get("sections", [])
    )
    return ActTemplate(
        id=data["id"],
        name=data["name"],
        category=data.get("category", "altro"),
        subcategory=data.get("subcategory"),
        description=data.get("description", ""),
        requires_modules=tuple(data.get("requires_modules") or []),
        slot_schema=data.get("slot_schema") or {},
        workflow_skip_steps=tuple(data.get("workflow_skip_steps") or []),
        sections=sections,
        tags=tuple(data.get("tags") or []),
    )


@lru_cache(maxsize=1)
def _load_all() -> dict[str, ActTemplate]:
    """Scansiona TEMPLATES_DIR per *.yaml e carica i template."""
    out: dict[str, ActTemplate] = {}
    if not TEMPLATES_DIR.is_dir():
        logger.warning("notai.templates.dir_missing", path=str(TEMPLATES_DIR))
        return out
    for path in TEMPLATES_DIR.glob("**/*.yaml"):
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            tpl = _parse_template(data, source_file=str(path))
            if tpl.id in out:
                logger.warning("notai.templates.duplicate_id", id=tpl.id, file=str(path))
                continue
            out[tpl.id] = tpl
        except Exception as e:  # noqa: BLE001
            logger.exception("notai.templates.load_failed", path=str(path), error=str(e))
    logger.info("notai.templates.loaded", count=len(out))
    return out


def get_template(template_id: str) -> ActTemplate | None:
    return _load_all().get(template_id)


def all_templates() -> list[ActTemplate]:
    return list(_load_all().values())


def templates_by_category(category: str) -> list[ActTemplate]:
    return [t for t in _load_all().values() if t.category == category]


def reload_templates() -> int:
    """Forza ricaricamento (usato in dev o dopo upload via admin)."""
    _load_all.cache_clear()
    return len(_load_all())


__all__ = [
    "ActTemplate",
    "SectionSpec",
    "all_templates",
    "get_template",
    "reload_templates",
    "templates_by_category",
]
