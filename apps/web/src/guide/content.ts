// Contenuti della Guida NotAI: sezioni navigabili con titolo, slug, body markdown-like.
// In Fase 5+ verranno migrate a file .md statici serviti dal backend.

export type GuideSection = {
  slug: string;
  title: string;
  category: "intro" | "domain" | "ai" | "admin" | "tech" | "compliance";
  summary: string;
  body: string;
};

export const GUIDE_SECTIONS: GuideSection[] = [
  // -----------------------------------------------------------------------
  // INTRO
  // -----------------------------------------------------------------------
  {
    slug: "benvenuto",
    title: "Benvenuto in NotAI",
    category: "intro",
    summary: "Cos'è NotAI e a chi serve.",
    body: `
NotAI è una piattaforma di automazione per studi notarili e legali italiani.

Aiuta il professionista a:

- **Standardizzare** il confezionamento degli atti notarili (compravendita, mutuo, donazione, successione, costituzione società).
- **Tracciare** ogni azione e ogni decisione del sistema in un audit forense con catena hash immutabile.
- **Ricercare** atti e clausole in modo puntuale per riferimenti normativi, parti, obblighi.
- **Integrarsi** con i portali pubblici (InfoCamere, ANPR, Catasto, Conservatoria, Agenzia Entrate).
- **Assistere** con AI locale, sempre sotto vincolo di **zero-allucinazione**: in caso di dubbio, il sistema passa il controllo al professionista.

L'app è organizzata in **moduli attivabili**: ogni studio può scegliere quali funzionalità utilizzare. Vedi la sezione "Moduli".
    `,
  },
  {
    slug: "primi-passi",
    title: "Primi passi",
    category: "intro",
    summary: "Come iniziare: bootstrap tenant, creazione pratica.",
    body: `
### 1. Accedi

In ambiente di sviluppo, il tenant viene creato via \`POST /api/v1/dev/bootstrap\` (vedi smoke script). In produzione: registrazione SSO/SAML (Fase 5+).

### 2. Crea una pratica

Dal menu **Pratiche** -> "Nuova". Specifica:

- Codice pratica (es. \`2026/0123\`)
- Tipo (es. \`notarile.compravendita.immobiliare\`, \`legale.civile\`)
- Titolo descrittivo
- Responsabile (opzionale)

### 3. Aggiungi atti alla pratica

Una pratica può contenere uno o più atti. Ogni atto ha il proprio workflow indipendente.

### 4. Avvia il workflow

Per atti notarili: il workflow esegue **visure pre-atto in parallelo**, genera la **bozza** da template, calcola le **imposte**, e apre un **HumanTask di review** per la conferma del notaio. Solo dopo l'approvazione l'atto procede verso firma e registrazione.
    `,
  },

  // -----------------------------------------------------------------------
  // DOMAIN
  // -----------------------------------------------------------------------
  {
    slug: "pratiche-atti-parti",
    title: "Pratiche, Atti, Parti",
    category: "domain",
    summary: "Modello dati del dominio.",
    body: `
La gerarchia base del dominio è:

- **Tenant** -> studio notarile/legale.
- **Practice** (Fascicolo) -> contenitore di lavoro per un cliente o operazione.
- **Act** (Atto) -> documento giuridico principale (es. compravendita, mutuo).
- **Party** (Parte) -> persona fisica (PF) o giuridica (PG) coinvolta in un atto.
- **PartyRole** -> associazione N:N Atto↔Parte con ruolo (venditore, acquirente, mandante…).

Ogni entità è **tenant-scoped**: la Row-Level Security su Postgres garantisce che il tenant A non veda mai dati del tenant B, neanche per bug applicativo.
    `,
  },
  {
    slug: "workflow-atto",
    title: "Workflow dell'Atto",
    category: "domain",
    summary: "Stati attraversati da un atto notarile.",
    body: `
Il workflow di un atto notarile è gestito da **Temporal** come processo durable. Stati attraversati (vedi \`WorkflowStatus\` enum):

1. **bozza** -> creazione atto
2. **visure_in_corso** -> visure pre-atto eseguite in **parallelo** (ANPR, Telemaco, Catasto…)
3. **draft_generated** -> bozza compilata dal template
4. **tax_calculated** -> imposte calcolate (registro, ipotecaria, catastale)
5. **review_requested** -> HumanTask aperto: notaio rivede
6. **review_completed** | **rejected** | **needs_changes** -> esito review

Ogni step produce un evento nell'**audit chain** dell'atto. I retry e i timeout sono gestiti da Temporal; il notaio può interrompere con un signal di cancel.
    `,
  },
  {
    slug: "tagging-ricerca",
    title: "Tagging e ricerca",
    category: "domain",
    summary: "Come navigare gli atti per riferimenti normativi.",
    body: `
Ogni clausola di un atto può essere taggata con:

- **Tipo atto**: \`act_type:notarile.compravendita.immobiliare\`
- **Ruolo parte**: \`party_role:venditore\`
- **Riferimento normativo**: \`norm:cc.art.2643\`, \`norm:dpr.131-1986.art.19.comma.1\`
- **Obbligo**: \`obligation:trascrizione\`, \`obligation:registro\`
- **Stato workflow**: \`wf_state:firmato\`
- **Periodo**: \`period:2026-Q2\`

I tag sono indicizzati su **OpenSearch** (BM25 + facet) e **Qdrant** (embedding semantici). Le query ibride permettono ricerche come *"clausole con art. 2643 c.c. negli atti del 2026"*.
    `,
  },

  // -----------------------------------------------------------------------
  // AI
  // -----------------------------------------------------------------------
  {
    slug: "ai-zero-allucinazione",
    title: "AI a zero-allucinazione",
    category: "ai",
    summary: "Il vincolo non-negoziabile dell'AI in NotAI.",
    body: `
**Principio fondante**: in materia giuridica nessuna allucinazione è tollerata. Il sistema deve **auto-riconoscere quando sta entrando in territorio creativo** e fermarsi, passando la palla al professionista.

### Strategia gerarchica

1. **Deterministico** prima: regole, template, regex, parsing strutturato. Copre il 70%+ dei task.
2. **LLM locale vincolato**: solo entro vincoli stretti:
   - Structured output obbligatorio (JSON schema)
   - Citation grounded verificata contro il KB
   - Allow-list dei task (riformulare, classificare, NON inventare)
   - Mai numeri (importi, date, CF, IBAN) dall'AI
3. **Abstention detector**: gate obbligatorio. 6 segnali combinati conservative-by-default.
4. **Hand-off umano**: HumanTask aperto con motivazione e candidati.

### Regole hard-coded

- Mai produrre numeri da LLM.
- Mai produrre testo giuridico senza citation grounded.
- Mai eseguire un'azione legale (firma, deposito) basata su output LLM senza conferma umana.
- Mai mostrare un output AI come "fatto certo": l'UI evidenzia sempre la provenienza AI.

### Trasparenza AI Act

Ogni call LLM produce:

- 1 record \`audit.audit_events\` nella catena hash (\`llm.invoked\` o \`ai.abstained\`)
- 1 record \`audit.llm_invocations\` con prompt, response, modello, temperature, seed, citazioni, rationale.

Conforme a **AI Act art. 11** (documentazione tecnica) e **art. 50** (trasparenza all'utente finale).
    `,
  },
  {
    slug: "ai-modelli-selezionabili",
    title: "Modelli LLM selezionabili",
    category: "ai",
    summary: "Come cambiare i modelli usati per ogni ruolo.",
    body: `
NotAI non parla mai di modelli specifici nel codice. Parla di **ruoli** applicativi:

- \`generation\` -> redrafting clausole, riassunti
- \`extraction\` -> estrazione dati strutturati da documenti
- \`embeddings\` -> vettorizzazione per RAG
- \`verifier\` -> cross-check per abstention
- \`classification\` -> classificazione zero/few-shot

Cambiando la mappa **ruolo → modello** (via env \`NOTAI_LLM_*\` o via UI runtime), si swappa il backend senza toccare il codice.

I modelli disponibili vengono scoperti automaticamente da:

- **LiteLLM** \`/v1/models\` -> alias esposti dal gateway
- **Ollama** \`/api/tags\` -> modelli installati sull'host (\`ollama pull ...\`)

Vai alla Dashboard per vedere i modelli installati e cambiare la mappa di routing.
    `,
  },

  // -----------------------------------------------------------------------
  // ADMIN
  // -----------------------------------------------------------------------
  {
    slug: "moduli",
    title: "Moduli: attivare e disattivare funzionalità",
    category: "admin",
    summary: "Come gestire i moduli del sistema.",
    body: `
NotAI è organizzato in **moduli** attivabili per tenant. Ogni modulo rappresenta una capacità funzionale (es. \`notaio.workflow\`, \`integrations.telemaco\`, \`ai.draft_suggestion\`).

### Categorie

- **core.\\*** -> sempre attivi (essenziali al funzionamento). Non disattivabili.
- **notaio.\\*** -> vertical notarile
- **legale.\\*** -> vertical avvocato
- **integrations.\\*** -> adapter portali pubblici
- **ai.\\*** -> moduli AI (richiedono Ollama o LLM equivalente)
- **audit.\\*** -> capacità di audit e conservazione

### Disattivare un modulo

Vai a **Moduli** → click sul toggle. Il sistema:

1. Persiste il flag in \`feature_flags\` (DB-scoped per tenant).
2. Registra un evento \`module.toggled\` nell'audit dello stream \`tenant-config:<tenant_id>\`.
3. Da quel momento, le route che richiedono il modulo restituiscono **HTTP 403** con detail strutturato.

### Tentativo di disattivare un core

Restituisce **HTTP 409 Conflict**: i moduli essenziali sono protetti dal sistema, non c'è modo di disattivarli (verrebbe meno la funzionalità base).

### Dipendenze tra moduli

Alcuni moduli richiedono altri (es. \`notaio.tax_calculator\` richiede \`notaio.workflow\`). L'UI mostra le dipendenze; l'enforcement runtime blocca le call se manca una dipendenza.
    `,
  },
  {
    slug: "audit-verifica",
    title: "Audit forense",
    category: "admin",
    summary: "Come verificare l'integrità della catena audit.",
    body: `
Ogni evento di dominio (creazione pratica, avvio workflow, chiamata LLM, toggle modulo) finisce in **\`audit.audit_events\`** con:

- \`prev_hash\`: hash dell'evento precedente nello stream
- \`hash\`: SHA-256(prev_hash + canonical_json(payload) + ts + actor)
- \`signature\`: firma del server (opzionale)
- \`timestamp_token\`: marca temporale RFC 3161 (opzionale)

### Garanzie

- Trigger Postgres bloccano UPDATE e DELETE (defense in depth oltre ai ruoli DB).
- Trigger sul TRUNCATE.
- Ruolo applicativo (\`notai_app\`) ha solo INSERT + SELECT sulla tabella.
- Canonicalization JSON RFC 8785 -> hash deterministico.

### Verifica catena

Da CLI nel container API:

\`\`\`
docker compose exec notai-api python -m apps.cli.audit_verify --tenant <UUID>
\`\`\`

Il comando ricalcola la catena hash di ogni stream e verifica match con i valori stored. Exit 0 se integra, 1 altrimenti.

### Export probatorio

Il modulo \`audit.export\` (se attivo) produce un bundle JSON firmato + catena hash + timestamp RFC 3161, verificabile offline da terzi (consulenti, periti, magistrati).
    `,
  },

  // -----------------------------------------------------------------------
  // TECH
  // -----------------------------------------------------------------------
  {
    slug: "architettura",
    title: "Architettura tecnica",
    category: "tech",
    summary: "Stack, moduli, deploy.",
    body: `
### Stack

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy async + Alembic
- **Frontend**: React 18 + Vite + TypeScript + TanStack Query
- **DB**: Postgres 16 con pgvector + Row-Level Security multi-tenant
- **Workflow**: Temporal 1.24 (durable execution + signals)
- **Object storage**: MinIO con object-lock WORM (conservazione)
- **Search**: OpenSearch (BM25) + Qdrant (vector) -> hybrid retrieval
- **Secret store**: HashiCorp Vault
- **LLM**: LiteLLM gateway davanti a Ollama (host) o vLLM (GPU)
- **Reverse proxy**: Caddy (TLS automatico)
- **Observability**: OpenTelemetry collector

### Layout codebase

\`\`\`
notai/
  contexts/         # bounded contexts DDD
    workflow/       # Temporal workflow + activities
    audit/          # event store + hash chain
    ai/             # LLM gateway + RAG + abstention detector
    integrations/   # adapter portali
    modules/        # feature flags + registry
    practices, parties, documents, search, iam, tax
  shared/           # tenancy, errors, domain base
apps/
  api/              # FastAPI
  workers/          # Temporal worker
  cli/              # CLI utilities (audit verify)
  web/              # React frontend
\`\`\`

### Containerizzazione

Tutta la soluzione è containerizzata. \`docker compose up\` da clean checkout porta lo stack a healthy in <5 min.
    `,
  },
  {
    slug: "api-reference",
    title: "API reference",
    category: "tech",
    summary: "Endpoint REST principali.",
    body: `
Vedi anche **OpenAPI**: \`http://localhost:8000/docs\`.

### Identità

- \`POST /api/v1/dev/bootstrap\` (solo dev) -> crea tenant + admin + emette JWT
- \`GET /api/v1/me\` -> info sull'utente corrente

### Pratiche / Atti

- \`POST /api/v1/practices\` -> crea pratica
- \`GET  /api/v1/practices\` -> lista pratiche
- \`POST /api/v1/acts\` -> crea atto
- \`POST /api/v1/acts/{id}/workflow/start\` -> avvia workflow (richiede modulo \`notaio.workflow\`)
- \`GET  /api/v1/acts/{id}/workflow/status\` -> stato workflow
- \`POST /api/v1/acts/{id}/workflow/human-review\` -> signal di approval/reject/changes

### AI

- \`POST /api/v1/ai/classify-clause\` -> classificazione clausola (richiede \`ai.classify_clause\` + \`ai.rag\`)
- \`POST /api/v1/ai/draft-suggestion\` -> redrafting (richiede \`ai.draft_suggestion\` + \`ai.rag\`)
- \`GET  /api/v1/ai/kb/stats\` -> stato knowledge base

### Moduli

- \`GET /api/v1/modules\` -> elenco completo + stato per il tenant
- \`PUT /api/v1/modules/{id}\` -> toggle modulo (409 sui core)

### Modelli LLM

- \`GET /api/v1/llm/models\` -> modelli scoperti (LiteLLM + Ollama)
- \`GET /api/v1/llm/routing\` -> mappa ruolo->modello
- \`PUT /api/v1/llm/routing\` -> override runtime
    `,
  },

  // -----------------------------------------------------------------------
  // COMPLIANCE
  // -----------------------------------------------------------------------
  {
    slug: "compliance",
    title: "Compliance e normative",
    category: "compliance",
    summary: "Checklist normative implementate e in roadmap.",
    body: `
### Implementato (Fase 0-4)

- **GDPR**: Multi-tenancy logica con RLS Postgres; crypto-shredding designed; audit trail.
- **L. 89/1913** (legge notarile) + DM 31/10/2006: repertorio numerazione (modulo \`notaio.repertorio\`).
- **eIDAS** Reg. UE 910/2014: firma qualificata via client desktop (componente non-containerizzata).
- **AI Act** Reg. UE 2024/1689: trasparenza art. 50 (provenienza AI tracciata per clausola), documentazione tecnica art. 11 (audit.llm_invocations).
- **AgID linee guida conservazione**: SInCRO UNI 11386 via conservatore accreditato (modulo \`audit.agid_conservation\`).

### Roadmap (Fase 5+)

- **D.Lgs 231/2007**: AUI art. 36, conservazione 10 anni, SOS UIF (modulo \`notaio.aml\` planned).
- **NIS2** D.Lgs 138/2024: incident reporting 24h/72h.
- **DPIA** documento + processo.
- **Codici deontologici** CNN + CNF: segreto professionale -> isolamento tenant rigoroso (già implementato).

### Considerazioni

NotAI non sostituisce il professionista: assiste compiti meccanici e linguistici. La responsabilità giuridica resta in capo al notaio/avvocato che firma l'atto.
    `,
  },
];

export const CATEGORY_LABELS: Record<GuideSection["category"], string> = {
  intro: "Introduzione",
  domain: "Dominio",
  ai: "AI",
  admin: "Amministrazione",
  tech: "Tecnico",
  compliance: "Compliance",
};
