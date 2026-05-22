# demorag/

Corpus di documenti per popolare la **Wiki / RAG** di NotAI come se fosse uno
studio reale. Tutti i contenuti qui dentro sono:

- **estratti normativi** parafrasati o citati da Normattiva (Codice Civile, CPC,
  TUR, ecc.) — sintesi e non testi integrali per restare leggeri e linkare la fonte;
- **formulari** di clausole e atti tipici, parafrasati per non violare diritti
  d'autore di formulari editoriali commerciali;
- **estratti di giurisprudenza** (massime) di Cassazione e tribunali di merito,
  sintetizzati nelle parti pertinenti;
- **note di dottrina** elementari (definizioni e principi consolidati).

Tutto il materiale è in **italiano** e pensato per ricerca semantica + BM25.

## Struttura

```
demorag/
  normattiva/                        <- estratti del Codice Civile, CPC, leggi speciali
    cc-art-1470-1547-compravendita.md
    cc-art-769-809-donazione.md
    cc-art-2463-2483-srl.md
    cpc-art-163-165-citazione.md
    cpc-art-633-656-decreto-ingiuntivo.md
    dl-132-2014-negoziazione-assistita.md
    dpr-131-1986-tur.md
    dlgs-347-1990-ipo-cat.md
  formulari-notarili/
    clausola-prezzo-bonifico-tracciato.md
    clausola-provenienza-libertà-pesi.md
    clausola-prima-casa.md
    clausola-mutuo-condizione-sospensiva.md
  formulari-legali/
    citazione-vocatio-petitum.md
    decreto-ingiuntivo-richiesta-tipica.md
    accordo-negoziazione-assistita.md
  giurisprudenza/
    cass-prima-casa-residenza.md
    cass-decreto-ingiuntivo-prova.md
  dottrina/
    principio-buona-fede-1366cc.md
```

## Come popolare la wiki

```bash
# Da CLI (carica tutto il corpus nella wiki del tenant demo)
docker compose -f compose.yml -f compose.dev.yml exec notai-api \
  python -m demorag.seed --tenant-slug studio-demo
```

Oppure dalla UI: Tab **Wiki → bottone "Importa corpus demo"** (TODO blocco 7c).

## Disclaimer

I testi normativi citati sono **estratti sintetici e parafrasati**.
Per uso operativo consultare sempre [Normattiva](https://www.normattiva.it/)
e la giurisprudenza ufficiale.
Nessun testo qui contenuto sostituisce la consulenza legale qualificata.
