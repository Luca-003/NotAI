# Case studies — documenti di input pre-pronti

Ogni sottocartella contiene i documenti di **input** che un notaio o avvocato
caricherebbe nel workspace per generare l'atto di output corrispondente.

Tutti i dati sono **fittizi** ma realistici nella forma. CF/PIVA sono validi
dal punto di vista dell'algoritmo di check ma non corrispondono a persone reali.

## Struttura

```
case-studies/
  compravendita-prima-casa/      <- notarile
    visura-catastale.md
    visura-ipocatastale.md
    documento-identita.md
    proposta-acquisto.md
  donazione-genitore-figlio/     <- notarile
    visura-catastale.md
    atto-provenienza.md
    stato-famiglia.md
  costituzione-srl/              <- notarile
    statuto-bozza.md
    visura-camerale-socio.md
    business-plan-sintesi.md
  citazione-recupero-credito/    <- legale
    fatture-insolute.md
    contratto-fornitura.md
    diffida-pagamento.md
  decreto-ingiuntivo-commerciale/ <- legale
    fatture-accettate.md
    estratto-conto-certificato.md
  separazione-consensuale/       <- legale
    accordo-coniugi.md
    atto-matrimonio.md
    situazione-patrimoniale.md
```

## Uso

1. Apri la pratica corrispondente in NotAI (dopo aver caricato lo `scenarios.yaml`).
2. Nella sezione **Workspace documenti** dell'atto, fai upload dei file `.md`
   di una sottocartella.
3. Aspetta che l'ingestion + classificazione completi (~5s per file).
4. Avvia il workflow: i chunk dei documenti caricati verranno linkati alle
   sezioni dell'atto generato (vedi pannello provenance e lineage graph).

## Disclaimer

Tutti i dati sono **fittizi**. Le clausole e i testi sono parafrasi sintetiche
di formule pubbliche; non riferimenti a documenti realmente esistenti.
