// Dettaglio atto: workflow controls (start, status polling, review).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, type Session } from "../auth";
import { Breadcrumb } from "../components/Breadcrumb";
import { buildHref, type Tab } from "../routing";
// apiFetch usato in mutations DraftViewer (provenance confirm/remove)
import { DocumentsWorkspace } from "./DocumentsWorkspace";
import { LineageGraph } from "./LineageGraph";
import { useDocumentProvenance } from "./hooks/useProvenance";
import { card } from "../theme";
import { pollWhile } from "../hooks/polling";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
import { s } from "../practices/PracticesPage";

type Act = {
  id: string;
  practice_id: string;
  kind: string;
  title: string;
  workflow_status: string;
  workflow_run_id: string | null;
};

type Visura = {
  source: string;
  found: boolean;
  hash: string;
  summary?: string;
  data?: Record<string, unknown>;
};

type WorkflowState = {
  status: string;
  visure: Visura[];
  draft: { document_id: string; sha256: string; storage_uri: string } | null;
  tax: { items: TaxItem[]; total: number } | null;
  review: { decision: string; user_id: string | null } | null;
};

type TaxItem = {
  tipo: string;
  aliquota?: number;
  base_imponibile?: number;
  importo: number;
  norm_ref: string;
};

type WorkflowStatusResponse = {
  workflow_id: string;
  status_temporal: string | null;
  state: WorkflowState;
};

type Party = {
  role: string;
  kind: "PF" | "PG";
  fiscal_code: string;
  vat?: string;
};

const ACTIVE_STATUSES = new Set([
  "visure_in_corso",
  "draft_in_corso",
  "draft_generated",
  "tax_calculated",
  "review_requested",
]);

export function ActDetail({
  session,
  actId,
  practiceTitle,
  practiceId,
  goto,
}: {
  session: Session;
  actId: string;
  practiceTitle: string;
  practiceId: string;
  goto: (tab: Tab, opts?: { practiceId?: string; actId?: string }) => void;
}) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _ = goto; // riservato a future navigation interne
  const qc = useQueryClient();
  const [showStart, setShowStart] = useState(false);
  // Stato condiviso per traceability: chunk evidenziato (selezionato dalle source
  // del DraftViewer) -> DocumentsWorkspace lo apre + scrolla.
  const [selectedSource, setSelectedSource] = useState<{
    documentId: string;
    chunkId: string;
  } | null>(null);

  const act = useQuery({
    queryKey: ["act", actId],
    queryFn: () => apiFetch<Act>(`/v1/acts/${actId}`, {}, session.token),
  });

  const wfStatus = useQuery({
    queryKey: ["wf-status", actId],
    queryFn: () =>
      apiFetch<WorkflowStatusResponse>(`/v1/acts/${actId}/workflow/status`, {}, session.token),
    enabled: !!act.data?.workflow_run_id,
    refetchInterval: pollWhile<WorkflowStatusResponse>(
      (data) => !data || ACTIVE_STATUSES.has(data.state.status),
      2_000,
    ),
  });

  const review = useMutation({
    mutationFn: (decision: "approved" | "rejected" | "changed") =>
      apiFetch(
        `/v1/acts/${actId}/workflow/human-review`,
        { method: "POST", body: JSON.stringify({ decision }) },
        session.token,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wf-status", actId] });
      qc.invalidateQueries({ queryKey: ["act", actId] });
    },
  });

  const currentStatus = wfStatus.data?.state.status ?? act.data?.workflow_status ?? "bozza";

  return (
    <div>
      <Breadcrumb
        crumbs={[
          { label: "Pratiche", href: buildHref("practices") },
          { label: practiceTitle, href: buildHref("practices", { practiceId }) },
          { label: act.data?.title ?? "Atto..." },
        ]}
      />

      {act.isLoading && <p style={{ marginTop: "1rem" }}>Carico...</p>}
      {act.isError && <div style={s.error}>{String(act.error)}</div>}

      {act.data && (
        <>
          <header style={{ marginBottom: "1.5rem" }}>
            <h1 style={{ margin: 0 }}>{act.data.title}</h1>
            <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
              <code style={s.kindBadge}>{act.data.kind}</code>
              <span style={s.statusBadge}>{currentStatus}</span>
            </div>
          </header>

          {/* Pannello "cosa fare adesso" - sempre visibile, contesto-aware */}
          <NextStepBanner
            status={currentStatus}
            hasWorkflow={!!act.data.workflow_run_id}
            showStart={showStart}
            onStart={() => setShowStart(true)}
          />

          <DocumentsWorkspace
            session={session}
            actId={actId}
            selectedSource={selectedSource}
            onClearSelection={() => setSelectedSource(null)}
          />

          {!act.data.workflow_run_id && !showStart && (
            <section style={card}>
              <h3 style={{ marginTop: 0 }}>2. Avvia il workflow</h3>
              <p style={{ color: "#475569" }}>
                Il workflow esegue le visure pre-atto (mock), genera la bozza dal
                template, calcola le imposte e apre la review per il notaio.
              </p>
              <button onClick={() => setShowStart(true)} style={{ ...s.primaryBtn, fontSize: "1rem", padding: "0.6rem 1.4rem" }}>
                ▶ Avvia workflow atto
              </button>
            </section>
          )}

          {showStart && (
            <StartWorkflowForm
              session={session}
              actId={actId}
              onStarted={() => {
                setShowStart(false);
                qc.invalidateQueries({ queryKey: ["act", actId] });
                qc.invalidateQueries({ queryKey: ["wf-status", actId] });
              }}
              onCancel={() => setShowStart(false)}
            />
          )}

          {act.data.workflow_run_id && wfStatus.data && (
            <WorkflowView
              state={wfStatus.data.state}
              statusTemporal={wfStatus.data.status_temporal}
              onReview={review.mutate}
              reviewPending={review.isPending}
              token={session.token}
              onSelectSource={(documentId, chunkId) =>
                setSelectedSource({ documentId, chunkId })
              }
            />
          )}
        </>
      )}
    </div>
  );
}

type TemplateSummary = {
  id: string;
  name: string;
  category: string;
  subcategory: string | null;
  description: string;
  tags: string[];
  section_count: number;
};

function StartWorkflowForm({
  session,
  actId,
  onStarted,
  onCancel,
}: {
  session: Session;
  actId: string;
  onStarted: () => void;
  onCancel: () => void;
}) {
  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: () =>
      apiFetch<{ grouped: Record<string, TemplateSummary[]>; templates: TemplateSummary[] }>(
        "/v1/templates",
        {},
        session.token,
      ),
    staleTime: 60_000,
  });

  const [parties, setParties] = useState<Party[]>([
    { role: "venditore", kind: "PF", fiscal_code: "RSSMRA70A01F205X" },
    { role: "acquirente", kind: "PF", fiscal_code: "BNCLCA85B05H501Y" },
  ]);
  const [baseImponibile, setBaseImponibile] = useState(250000);
  const [isPrimaCasa, setIsPrimaCasa] = useState(true);
  const [templateId, setTemplateId] = useState("notarile.compravendita.immobiliare:v1");

  const selectedTemplate = templates.data?.templates.find((t) => t.id === templateId);
  const isNotarile = templateId.startsWith("notarile.");

  const start = useMutation({
    mutationFn: () =>
      apiFetch(
        `/v1/acts/${actId}/workflow/start`,
        {
          method: "POST",
          body: JSON.stringify({
            template_id: templateId,
            base_imponibile: baseImponibile,
            is_prima_casa: isPrimaCasa,
            parties,
          }),
        },
        session.token,
      ),
    onSuccess: () => onStarted(),
  });

  const setParty = (idx: number, patch: Partial<Party>) => {
    setParties(parties.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  };

  const addParty = () =>
    setParties([...parties, { role: "altra_parte", kind: "PF", fiscal_code: "" }]);
  const removeParty = (idx: number) => setParties(parties.filter((_, i) => i !== idx));

  return (
    <section style={card}>
      <h3 style={{ marginTop: 0 }}>Avvia workflow</h3>
      <div style={s.formGrid}>
        <label style={{ ...s.field, gridColumn: "1 / -1" }}>
          <span style={s.fieldLabel}>Template atto</span>
          <select
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            style={s.input}
          >
            {templates.isLoading && <option>Carico template…</option>}
            {templates.data && Object.entries(templates.data.grouped).map(([cat, tlist]) => (
              <optgroup key={cat} label={cat.toUpperCase()}>
                {tlist.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.id})
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          {selectedTemplate && (
            <span style={{ fontSize: "0.8rem", color: "#64748b", marginTop: "0.25rem" }}>
              {selectedTemplate.description} · {selectedTemplate.section_count} sezioni
            </span>
          )}
        </label>
        <label style={s.field}>
          <span style={s.fieldLabel}>
            {isNotarile ? "Base imponibile (EUR)" : "Valore causa / credito (EUR)"}
          </span>
          <input
            type="number"
            value={baseImponibile}
            onChange={(e) => setBaseImponibile(Number(e.target.value))}
            style={s.input}
          />
        </label>
        {isNotarile && (
          <label style={{ ...s.field, alignSelf: "end" }}>
            <span style={s.fieldLabel}>
              <input
                type="checkbox"
                checked={isPrimaCasa}
                onChange={(e) => setIsPrimaCasa(e.target.checked)}
                style={{ marginRight: "0.4rem" }}
              />
              prima casa
            </span>
          </label>
        )}
      </div>

      <h4 style={{ marginBottom: "0.5rem" }}>Parti</h4>
      {parties.map((p, idx) => (
        <div key={idx} style={partyRow}>
          <input
            value={p.role}
            onChange={(e) => setParty(idx, { role: e.target.value })}
            placeholder="ruolo"
            style={{ ...s.input, flex: 1 }}
          />
          <select
            value={p.kind}
            onChange={(e) => setParty(idx, { kind: e.target.value as "PF" | "PG" })}
            style={{ ...s.input, width: 80 }}
          >
            <option value="PF">PF</option>
            <option value="PG">PG</option>
          </select>
          <input
            value={p.fiscal_code}
            onChange={(e) => setParty(idx, { fiscal_code: e.target.value })}
            placeholder="codice fiscale"
            style={{ ...s.input, flex: 2 }}
          />
          <button onClick={() => removeParty(idx)} style={s.secondaryBtn}>−</button>
        </div>
      ))}
      <button onClick={addParty} style={{ ...s.secondaryBtn, marginBottom: "1rem" }}>+ aggiungi parte</button>

      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button onClick={() => start.mutate()} disabled={start.isPending || parties.length === 0} style={s.primaryBtn}>
          {start.isPending ? "Avvio..." : "Avvia"}
        </button>
        <button onClick={onCancel} style={s.secondaryBtn}>Annulla</button>
      </div>
      {start.isError && <div style={s.error}>{String(start.error)}</div>}
    </section>
  );
}

function WorkflowView({
  state,
  statusTemporal,
  onReview,
  reviewPending,
  token,
  onSelectSource,
}: {
  state: WorkflowState;
  statusTemporal: string | null;
  onReview: (decision: "approved" | "rejected" | "changed") => void;
  reviewPending: boolean;
  token: string;
  onSelectSource: (documentId: string, chunkId: string) => void;
}) {
  return (
    <>
      <section style={card}>
        <h3 style={{ marginTop: 0 }}>Stato workflow</h3>
        <p>
          <strong>App status:</strong> <span style={s.statusBadge}>{state.status}</span>
          {" "}
          <strong style={{ marginLeft: "1rem" }}>Temporal:</strong>{" "}
          <code style={s.kindBadge}>{statusTemporal ?? "—"}</code>
        </p>

        <ProgressSteps status={state.status} />
      </section>

      {state.visure.length > 0 && <VisureSection visure={state.visure} />}

      {state.draft && <DraftViewer draft={state.draft} token={token} onSelectSource={onSelectSource} />}

      {state.tax && (
        <section style={card}>
          <h3 style={{ marginTop: 0 }}>Calcolo imposte</h3>
          <table style={s.table}>
            <thead>
              <tr>
                <th style={s.th}>Tipo</th>
                <th style={s.th}>Base</th>
                <th style={s.th}>Aliquota</th>
                <th style={s.th}>Importo</th>
                <th style={s.th}>Norma</th>
              </tr>
            </thead>
            <tbody>
              {state.tax.items.map((it, i) => (
                <tr key={i}>
                  <td style={s.td}>{it.tipo}</td>
                  <td style={s.td}>{it.base_imponibile ? `${it.base_imponibile.toLocaleString("it-IT")} €` : "—"}</td>
                  <td style={s.td}>{it.aliquota ? `${(it.aliquota * 100).toFixed(1)}%` : "—"}</td>
                  <td style={s.td}><strong>{it.importo.toLocaleString("it-IT")} €</strong></td>
                  <td style={s.td}><code style={{ fontSize: "0.78rem" }}>{it.norm_ref}</code></td>
                </tr>
              ))}
              <tr>
                <td style={{ ...s.td, fontWeight: 700 }} colSpan={3}>Totale</td>
                <td style={{ ...s.td, fontWeight: 700 }}>{state.tax.total.toLocaleString("it-IT")} €</td>
                <td style={s.td} />
              </tr>
            </tbody>
          </table>
        </section>
      )}

      {state.status === "review_requested" && !state.review && (
        <section style={{ ...card, background: "#fef3c7", borderColor: "#f59e0b" }}>
          <h3 style={{ marginTop: 0 }}>Conferma del notaio richiesta</h3>
          <p>
            Il workflow è in attesa della tua decisione. Verifica visure, bozza e imposte,
            poi scegli:
          </p>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button onClick={() => onReview("approved")} disabled={reviewPending} style={{ ...s.primaryBtn, background: "#16a34a" }}>
              ✓ Approva e procedi
            </button>
            <button onClick={() => onReview("changed")} disabled={reviewPending} style={s.secondaryBtn}>
              Richiedi modifiche
            </button>
            <button onClick={() => onReview("rejected")} disabled={reviewPending} style={{ ...s.secondaryBtn, color: "#b91c1c", borderColor: "#fca5a5" }}>
              ✕ Rifiuta
            </button>
          </div>
        </section>
      )}

      {state.review && (
        <section style={card}>
          <h3 style={{ marginTop: 0 }}>Esito review</h3>
          <p>
            Decisione: <strong style={{ color: state.review.decision === "approved" ? "#16a34a" : "#b91c1c" }}>{state.review.decision}</strong>
          </p>
        </section>
      )}
    </>
  );
}

const STEPS = [
  { id: "visure_in_corso", label: "Visure" },
  { id: "draft_generated", label: "Bozza" },
  { id: "tax_calculated", label: "Imposte" },
  { id: "review_requested", label: "Review notaio" },
  { id: "review_completed", label: "Firmato" },
];

function ProgressSteps({ status }: { status: string }) {
  const idx = STEPS.findIndex((s) => s.id === status);
  const completed = status === "review_completed";
  return (
    <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", flexWrap: "wrap" }}>
      {STEPS.map((step, i) => {
        const done = idx > i || completed;
        const current = i === idx && !completed;
        return (
          <div
            key={step.id}
            style={{
              padding: "0.4rem 0.9rem",
              borderRadius: 4,
              fontSize: "0.85rem",
              fontWeight: current ? 700 : 500,
              background: current ? "#1e293b" : done ? "#16a34a" : "#e2e8f0",
              color: current || done ? "white" : "#64748b",
            }}
          >
            {done ? "✓ " : ""}{step.label}
          </div>
        );
      })}
    </div>
  );
}

function VisureSection({ visure }: { visure: Visura[] }) {
  return (
    <section style={card}>
      <h3 style={{ marginTop: 0 }}>Visure acquisite automaticamente</h3>
      <div style={{ display: "grid", gap: "0.75rem" }}>
        {visure.map((v, i) => (
          <div key={i} style={{ border: "1px solid #e2e8f0", borderRadius: 4, padding: "0.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.4rem" }}>
              <strong>{v.source.toUpperCase()}</strong>
              <span
                style={{
                  fontSize: "0.78rem",
                  padding: "0.1rem 0.5rem",
                  borderRadius: 999,
                  background: v.found ? "#dcfce7" : "#fee2e2",
                  color: v.found ? "#166534" : "#7f1d1d",
                  fontWeight: 600,
                }}
              >
                {v.found ? "✓ trovata" : "✕ non trovata"}
              </span>
            </div>
            {v.summary && <div style={{ marginBottom: "0.4rem", color: "#1e293b" }}>{v.summary}</div>}
            {v.data && Object.keys(v.data).length > 0 && (
              <details>
                <summary style={{ cursor: "pointer", fontSize: "0.85rem", color: "#64748b" }}>
                  Mostra dati grezzi
                </summary>
                <pre style={{ fontSize: "0.78rem", background: "#f8fafc", padding: "0.5rem", borderRadius: 3, overflow: "auto", maxHeight: 300 }}>
                  {JSON.stringify(v.data, null, 2)}
                </pre>
              </details>
            )}
            <div style={{ fontSize: "0.72rem", color: "#94a3b8", marginTop: "0.3rem" }}>
              hash riproducibile: <code>{v.hash.slice(0, 16)}…</code>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

type DraftSection = {
  id: string;
  title: string;
  text: string;
  sources?: { chunk_id: string; source_document_id: string; entity_type?: string; document_type?: string }[];
};

function DraftViewer({
  draft,
  token,
  onSelectSource,
}: {
  draft: { document_id: string; sha256: string; storage_uri: string };
  token: string;
  onSelectSource: (documentId: string, chunkId: string) => void;
}) {
  const qc = useQueryClient();
  const [showLineage, setShowLineage] = useState(false);

  const sections = useQuery({
    queryKey: ["doc-sections", draft.document_id],
    queryFn: () =>
      apiFetch<{ sections: DraftSection[]; filename: string }>(
        `/v1/documents/${draft.document_id}/sections`,
        {},
        token,
      ),
  });

  const provenance = useDocumentProvenance(draft.document_id, token);

  const confirmLink = useMutation({
    mutationFn: ({ id, confirmed }: { id: string; confirmed: boolean }) =>
      apiFetch(
        `/v1/documents/provenance/${id}/confirm`,
        { method: "PUT", body: JSON.stringify({ confirmed }) },
        token,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["doc-provenance", draft.document_id] }),
  });

  const removeLink = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/v1/documents/provenance/${id}`, { method: "DELETE" }, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["doc-provenance", draft.document_id] }),
  });

  const rawContent = useQuery({
    queryKey: ["doc-content", draft.document_id],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/v1/documents/${draft.document_id}/content`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.text();
    },
  });

  const download = () => {
    if (!rawContent.data) return;
    const blob = new Blob([rawContent.data], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bozza-${draft.document_id.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const secs = sections.data?.sections ?? [];

  return (
    <section style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Documento atto (bozza)</h3>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button onClick={() => setShowLineage((v) => !v)} style={s.secondaryBtn}>
            {showLineage ? "▼ nascondi lineage" : "▶ vedi lineage grafico"}
          </button>
          <button onClick={download} disabled={!rawContent.data} style={s.primaryBtn}>
            ⬇ Scarica .md
          </button>
        </div>
      </div>

      {showLineage && (
        <div style={{ marginBottom: "0.75rem" }}>
          <LineageGraph
            documentId={draft.document_id}
            token={token}
            onSelectChunk={(docId, chunkId) => onSelectSource(docId, chunkId)}
          />
        </div>
      )}
      <div style={{ fontSize: "0.8rem", color: "#64748b", marginBottom: "0.75rem" }}>
        <code>{draft.document_id}</code> · sha256 <code>{draft.sha256.slice(0, 16)}…</code>
        {provenance.data && (
          <span style={{ marginLeft: "0.75rem" }}>
            · <strong>{provenance.data.total_links}</strong> link di provenienza ai chunk di input
          </span>
        )}
      </div>

      {sections.isLoading && <p>Carico sezioni...</p>}
      {sections.isError && (
        <div style={{ background: "#fee2e2", color: "#7f1d1d", padding: "0.5rem 0.75rem", borderRadius: 4 }}>
          Errore: {String(sections.error)}
        </div>
      )}

      {secs.length > 0 && (
        <div style={{
          background: "#fafaf9",
          border: "1px solid #e7e5e4",
          borderRadius: 4,
          padding: "1rem 1.25rem",
          maxHeight: 640,
          overflowY: "auto",
        }}>
          {secs.map((sec) => {
            const links = provenance.data?.links_by_section[sec.id] ?? [];
            return (
              <article
                key={sec.id}
                style={{
                  marginBottom: "1.2rem",
                  borderLeft: links.length > 0 ? "3px solid #16a34a" : "3px solid transparent",
                  paddingLeft: "0.8rem",
                }}
              >
                <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.5rem" }}>
                  <h4 style={{ margin: 0, fontFamily: "Georgia, serif", color: "#0f172a" }}>{sec.title}</h4>
                  {links.length > 0 ? (
                    <details style={{ fontSize: "0.78rem" }}>
                      <summary style={{ cursor: "pointer", color: "#16a34a", fontWeight: 600 }}>
                        ⓘ {links.length} font{links.length === 1 ? "e" : "i"}
                      </summary>
                      <ul style={{ paddingLeft: "1rem", margin: "0.4rem 0", color: "#475569" }}>
                        {links.map((l) => (
                          <li key={l.id} style={{ marginBottom: "0.3rem" }}>
                            <code style={{ fontSize: "0.7rem", background: "#f1f5f9", padding: "0 0.3rem", borderRadius: 2 }}>
                              {l.relation}
                            </code>{" "}
                            {l.rationale ?? ""}{" "}
                            <span style={{ color: "#94a3b8" }}>
                              (conf {(l.confidence * 100).toFixed(0)}%)
                            </span>{" "}
                            <button
                              onClick={() =>
                                onSelectSource(l.source_document_id, l.source_chunk_id)
                              }
                              style={{
                                marginLeft: "0.4rem",
                                padding: "0.1rem 0.4rem",
                                fontSize: "0.7rem",
                                background: "#1e293b",
                                color: "white",
                                border: "none",
                                borderRadius: 3,
                                cursor: "pointer",
                              }}
                              title="Apri il chunk sorgente nel workspace"
                            >
                              ↗ apri fonte
                            </button>
                            <button
                              onClick={() => confirmLink.mutate({ id: l.id, confirmed: true })}
                              disabled={confirmLink.isPending || l.confidence === 1.0}
                              style={{
                                marginLeft: "0.3rem",
                                padding: "0.1rem 0.4rem",
                                fontSize: "0.7rem",
                                background: l.confidence === 1.0 ? "#dcfce7" : "#16a34a",
                                color: l.confidence === 1.0 ? "#166534" : "white",
                                border: "none",
                                borderRadius: 3,
                                cursor: "pointer",
                              }}
                              title="Conferma che questo link e' corretto"
                            >
                              {l.confidence === 1.0 ? "✓ confermato" : "✓ conferma"}
                            </button>
                            <button
                              onClick={() => {
                                if (confirm("Rimuovere questo link? L'azione e' tracciata in audit.")) {
                                  removeLink.mutate(l.id);
                                }
                              }}
                              disabled={removeLink.isPending}
                              style={{
                                marginLeft: "0.3rem",
                                padding: "0.1rem 0.4rem",
                                fontSize: "0.7rem",
                                background: "white",
                                color: "#b91c1c",
                                border: "1px solid #fca5a5",
                                borderRadius: 3,
                                cursor: "pointer",
                              }}
                              title="Rimuovi link errato"
                            >
                              ✗ rimuovi
                            </button>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : (
                    <span style={{ fontSize: "0.72rem", color: "#94a3b8" }}>(nessuna fonte collegata)</span>
                  )}
                </header>
                <div style={{
                  fontFamily: "Georgia, 'Times New Roman', serif",
                  lineHeight: 1.65,
                  whiteSpace: "pre-wrap",
                  fontSize: "0.93rem",
                  color: "#1c1917",
                  marginTop: "0.4rem",
                }}>
                  {sec.text}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {secs.length === 0 && rawContent.data && (
        <article style={{
          background: "#fafaf9",
          border: "1px solid #e7e5e4",
          borderRadius: 4,
          padding: "1.25rem 1.5rem",
          maxHeight: 560,
          overflowY: "auto",
          fontFamily: "Georgia, serif",
          whiteSpace: "pre-wrap",
        }}>
          {rawContent.data}
        </article>
      )}
    </section>
  );
}

const partyRow: React.CSSProperties = {
  display: "flex",
  gap: "0.5rem",
  marginBottom: "0.4rem",
  alignItems: "center",
};

// ---------------------------------------------------------------------------
// NextStepBanner — pannello "cosa fare adesso", visible all the time per
// orientare il notaio. Cambia copy + colore in base allo stato del workflow.
// ---------------------------------------------------------------------------

function NextStepBanner({
  status,
  hasWorkflow,
  showStart,
  onStart,
}: {
  status: string;
  hasWorkflow: boolean;
  showStart: boolean;
  onStart: () => void;
}) {
  type Step = { title: string; body: string; cta?: { label: string; onClick: () => void } | null; tone: "info" | "action" | "done" };
  let step: Step;

  if (!hasWorkflow && !showStart) {
    step = {
      tone: "action",
      title: "1. Carica i documenti di input",
      body:
        "Trascina (o usa 'Aggiungi file') i documenti dell'atto nel workspace qui sotto: visure catastali, ipocatastali, contratti, documenti d'identita'. Il sistema li classifica e tagga automaticamente.",
      cta: null,
    };
  } else if (!hasWorkflow && showStart) {
    step = {
      tone: "action",
      title: "2. Configura e avvia il workflow",
      body:
        "Seleziona il template dell'atto, conferma le parti e l'imponibile. Il workflow farà visure mock, genera la bozza e calcola le imposte.",
      cta: null,
    };
  } else if (status === "visure_in_corso" || status === "draft_in_corso") {
    step = {
      tone: "info",
      title: `Workflow in corso: ${status}`,
      body:
        "Il sistema sta lavorando: visure parallele, generazione bozza, calcolo imposte. Pochi secondi.",
      cta: null,
    };
  } else if (status === "review_requested") {
    step = {
      tone: "action",
      title: "3. Review del notaio",
      body:
        "Tutto pronto. Controlla visure + bozza + imposte qui sotto, e usa i bottoni 'Approva' / 'Modifiche' / 'Rifiuta' nella sezione gialla.",
      cta: null,
    };
  } else if (status === "review_completed") {
    step = {
      tone: "done",
      title: "Atto firmato",
      body:
        "La review e' stata approvata. In produzione segue firma qualificata + registrazione + conservazione.",
      cta: null,
    };
  } else {
    step = {
      tone: "info",
      title: `Stato: ${status}`,
      body: "",
      cta: null,
    };
  }

  // Hint sull'azione di avvio workflow se sei nello step 1 e hai docs ma non hai
  // ancora avviato.
  if (!hasWorkflow && !showStart) {
    step.cta = { label: "Salta upload e avvia subito", onClick: onStart };
  }

  const palette: Record<Step["tone"], { bg: string; border: string; fg: string }> = {
    action: { bg: "#eff6ff", border: "#3b82f6", fg: "#1e3a8a" },
    info: { bg: "#f8fafc", border: "#94a3b8", fg: "#1e293b" },
    done: { bg: "#dcfce7", border: "#16a34a", fg: "#14532d" },
  };
  const p = palette[step.tone];

  return (
    <section
      style={{
        background: p.bg,
        borderLeft: `4px solid ${p.border}`,
        borderRadius: 4,
        padding: "0.9rem 1.25rem",
        marginBottom: "1rem",
      }}
    >
      <h3 style={{ margin: 0, color: p.fg, fontSize: "1.05rem" }}>{step.title}</h3>
      {step.body && (
        <p style={{ margin: "0.4rem 0 0", color: p.fg, fontSize: "0.92rem" }}>{step.body}</p>
      )}
      {step.cta && (
        <button
          onClick={step.cta.onClick}
          style={{
            marginTop: "0.75rem",
            padding: "0.45rem 1rem",
            background: p.border,
            color: "white",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
            fontWeight: 600,
            fontSize: "0.9rem",
          }}
        >
          {step.cta.label}
        </button>
      )}
    </section>
  );
}
