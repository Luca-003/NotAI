// Dettaglio atto: workflow controls (start, status polling, review).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, type Session } from "../auth";
import { DocumentsWorkspace } from "./DocumentsWorkspace";

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
  onBack,
}: {
  session: Session;
  actId: string;
  onBack: () => void;
}) {
  const qc = useQueryClient();
  const [showStart, setShowStart] = useState(false);

  const act = useQuery({
    queryKey: ["act", actId],
    queryFn: () => apiFetch<Act>(`/v1/acts/${actId}`, {}, session.token),
  });

  const wfStatus = useQuery({
    queryKey: ["wf-status", actId],
    queryFn: () =>
      apiFetch<WorkflowStatusResponse>(`/v1/acts/${actId}/workflow/status`, {}, session.token),
    enabled: !!act.data?.workflow_run_id,
    refetchInterval: (q) => {
      const data = q.state.data as WorkflowStatusResponse | undefined;
      if (!data) return 3_000;
      return ACTIVE_STATUSES.has(data.state.status) ? 2_000 : false;
    },
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

  return (
    <div>
      <button onClick={onBack} style={s.secondaryBtn}>← Pratica</button>

      {act.isLoading && <p style={{ marginTop: "1rem" }}>Carico...</p>}
      {act.isError && <div style={s.error}>{String(act.error)}</div>}

      {act.data && (
        <>
          <header style={{ marginTop: "1rem", marginBottom: "1.5rem" }}>
            <h1 style={{ margin: 0 }}>{act.data.title}</h1>
            <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
              <code style={s.kindBadge}>{act.data.kind}</code>
              <span style={s.statusBadge}>{act.data.workflow_status}</span>
            </div>
          </header>

          <DocumentsWorkspace session={session} actId={actId} />

          {!act.data.workflow_run_id && !showStart && (
            <section style={card}>
              <h3 style={{ marginTop: 0 }}>Workflow non avviato</h3>
              <p style={{ color: "#475569" }}>
                Avvia il workflow per eseguire le visure pre-atto, generare la bozza,
                calcolare le imposte e aprire la review.
              </p>
              <button onClick={() => setShowStart(true)} style={s.primaryBtn}>
                Avvia workflow atto
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
            <WorkflowView state={wfStatus.data.state} statusTemporal={wfStatus.data.status_temporal} onReview={review.mutate} reviewPending={review.isPending} />
          )}
        </>
      )}
    </div>
  );
}

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
  const [parties, setParties] = useState<Party[]>([
    { role: "venditore", kind: "PF", fiscal_code: "RSSMRA70A01F205X" },
    { role: "acquirente", kind: "PF", fiscal_code: "BNCLCA85B05H501Y" },
  ]);
  const [baseImponibile, setBaseImponibile] = useState(250000);
  const [isPrimaCasa, setIsPrimaCasa] = useState(true);
  const [templateId, setTemplateId] = useState("notarile.compravendita.immobiliare:v1");

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
        <label style={s.field}>
          <span style={s.fieldLabel}>Template ID</span>
          <input value={templateId} onChange={(e) => setTemplateId(e.target.value)} style={s.input} />
        </label>
        <label style={s.field}>
          <span style={s.fieldLabel}>Base imponibile (EUR)</span>
          <input
            type="number"
            value={baseImponibile}
            onChange={(e) => setBaseImponibile(Number(e.target.value))}
            style={s.input}
          />
        </label>
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
}: {
  state: WorkflowState;
  statusTemporal: string | null;
  onReview: (decision: "approved" | "rejected" | "changed") => void;
  reviewPending: boolean;
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

      {state.draft && <DraftViewer draft={state.draft} />}

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
  return (
    <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", flexWrap: "wrap" }}>
      {STEPS.map((step, i) => {
        const done = idx > i || (idx === STEPS.length - 1 && status === "review_completed");
        const current = i === idx;
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

type ProvLink = {
  id: string;
  source_chunk_id: string;
  source_document_id: string;
  relation: string;
  rationale: string | null;
  confidence: number;
};

function DraftViewer({
  draft,
}: {
  draft: { document_id: string; sha256: string; storage_uri: string };
}) {
  const token = localStorage.getItem("notai.jwt");

  const sections = useQuery({
    queryKey: ["doc-sections", draft.document_id],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/v1/documents/${draft.document_id}/sections`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()) as { sections: DraftSection[]; filename: string };
    },
  });

  const provenance = useQuery({
    queryKey: ["doc-provenance", draft.document_id],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/v1/documents/${draft.document_id}/provenance`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()) as { links_by_section: Record<string, ProvLink[]>; total_links: number };
    },
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
        <button onClick={download} disabled={!rawContent.data} style={s.primaryBtn}>
          ⬇ Scarica .md
        </button>
      </div>
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
                            </span>
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

const card: React.CSSProperties = {
  background: "white",
  border: "1px solid #e2e8f0",
  borderRadius: 6,
  padding: "1rem 1.25rem",
  marginBottom: "1rem",
};

const partyRow: React.CSSProperties = {
  display: "flex",
  gap: "0.5rem",
  marginBottom: "0.4rem",
  alignItems: "center",
};
