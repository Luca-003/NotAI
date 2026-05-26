"""Probe hardware Ollama: rileva GPU/RAM/modelli caricati.

Usato all'avvio dell'API per loggare la baseline + suggerire concorrenza.
NON modifica configurazione: l'utente decide se alzare NOTAI_CLASSIFY_CONCURRENCY.

Esempio output log:
    notai.hw.ollama_probe gpu=true vram_mb=8192 ram_mb=16384 loaded_models=[qwen2.5:3b]
    notai.hw.suggestion: GPU rilevata, puoi alzare NOTAI_CLASSIFY_CONCURRENCY a 5-10
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


async def probe_ollama() -> dict:
    """Probe non-bloccante a Ollama. Best-effort: errori loggati ma non sollevati.

    Output:
        {
          "reachable": bool,
          "loaded_models": [name, ...],
          "has_gpu": bool,
          "vram_total_mb": int | None,
          "suggestion": str | None,
        }
    """
    out: dict = {
        "reachable": False,
        "loaded_models": [],
        "has_gpu": False,
        "vram_total_mb": None,
        "suggestion": None,
    }

    try:
        import httpx
        from notai.config import get_settings

        settings = get_settings()
        url = settings.llm_routing.ollama_discovery_url

        async with httpx.AsyncClient(timeout=5.0) as client:
            # /api/ps: modelli caricati in memoria (in tempo reale)
            ps_resp = await client.get(f"{url}/api/ps")
            ps_data = ps_resp.json() if ps_resp.status_code == 200 else {}

        out["reachable"] = True
        models = ps_data.get("models", []) or []
        total_vram = 0
        any_gpu = False
        for m in models:
            out["loaded_models"].append(m.get("name", "?"))
            vram = m.get("size_vram") or 0
            if vram > 0:
                any_gpu = True
                total_vram = max(total_vram, vram)

        out["has_gpu"] = any_gpu
        if total_vram > 0:
            out["vram_total_mb"] = total_vram // (1024 * 1024)

        # Suggestion
        if any_gpu:
            out["suggestion"] = (
                "GPU rilevata in Ollama: puoi alzare NOTAI_CLASSIFY_CONCURRENCY "
                "a 5-10 per accelerare la classificazione."
            )
        elif models:
            out["suggestion"] = (
                "Ollama gira su CPU. Default NOTAI_CLASSIFY_CONCURRENCY=2 e' "
                "appropriato. Considera cloud (Groq/Gemini) per demo veloce."
            )
        # Se models e' vuota e ollama e' reachable, l'utente non ha ancora
        # fatto pull del modello -> niente suggestion (gestito a runtime).

    except Exception as e:  # noqa: BLE001
        # Best-effort: Ollama potrebbe non essere su, ma l'app continua.
        logger.debug("notai.hw.ollama_probe_failed", error=str(e))

    return out


async def log_hardware_baseline() -> None:
    """Chiamabile da lifespan() dell'API. Logga lo stato hardware + suggestion."""
    info = await probe_ollama()
    logger.info(
        "notai.hw.ollama_probe",
        reachable=info["reachable"],
        loaded_models=info["loaded_models"],
        has_gpu=info["has_gpu"],
        vram_total_mb=info["vram_total_mb"],
    )
    if info["suggestion"]:
        logger.info("notai.hw.suggestion", message=info["suggestion"])


__all__ = ["probe_ollama", "log_hardware_baseline"]
