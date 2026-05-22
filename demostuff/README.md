# demostuff/

Scenari di demo per testare NotAI end-to-end **come un notaio**.

I dati qui dentro sono **fittizi** ma realistici nella forma. Servono a:

1. Pre-popolare il tenant demo con pratiche/atti/parti pronti per workflow.
2. Mostrare il flusso completo (visure mock → bozza → imposte → review → audit).
3. Demo commerciali per investitori/clienti potenziali.

## Contenuto

- `scenarios.yaml` — 3 scenari completi (compravendita prima casa, donazione, costituzione SRL).
- `clauses_examples.md` — clausole tipiche parafrasate per i template (NON copiate da formulario coperto da copyright).
- `seed.py` — script per caricare gli scenari nel DB tramite l'API. Eseguibile dal container API.

## Fonti

I testi delle clausole sono parafrasi sintetiche di formule pubbliche in uso negli atti notarili italiani (es. art. 1470, 2643 c.c.). I riferimenti normativi puntano a Normattiva.

Le anagrafiche fittizie usano:
- Codici fiscali generati con algoritmo standard (validi nella forma).
- Indirizzi reali pubblici (vie e CAP esistenti, civici inventati).
- Nomi/cognomi italiani comuni.

## Uso

### Da UI (raccomandato per demo)

1. Accedi (button verde "Accedi (dev)" in topbar).
2. Dashboard → click "Carica scenari demo" (button arancione).
3. Vai a tab "Pratiche" → vedi 3 pratiche pronte da aprire.

### Da CLI

```bash
docker compose -f compose.yml -f compose.dev.yml exec notai-api \
  python -m demostuff.seed --tenant-slug studio-demo
```

## Disclaimer

Tutti i dati sono **fittizi** e non riferiti a persone, immobili o società esistenti.
Per uso solo in ambiente di sviluppo / test.
