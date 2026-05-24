// ActPreparation: vista dell'atto PRIMA del workflow Temporal.
// Articola in step espliciti la fase di consolidamento documenti:
//   1. Catalogo  (automatico: ingestion + classify)
//   2. Visure needed (cosa il template chiede e non e' presente)
//   3. Visure acquisite (mock adapter -> Document)
//   4. Anteprima slot estratti (LLM extract preview)
//   5. Consolida (notaio approva, sblocca workflow)

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiFetch, type Session } from "../auth";
import { DocumentsWorkspace } from "./DocumentsWorkspace";
import { pollWhile } from "../hooks/polling";

type SlotProvenance = {
  chunk_id: string | null;
  char_start: number | null;
  char_end: number | null;
  confidence: number;
};

type PreviewSlots = {
  slots: Record<string, string | number | boolean | null>;
  provenance: Record<string, SlotProvenance>;
  abstained: string[];
  extracted_at: string;
  template_id: string;
};

type PrepStatus = {
  act_id: string;
  template_id: string;
  template_known: boolean;
  step1_catalog: {
    documents_total: number;
    documents_classified: number;
    chunks_total: number;
    chunks_classified: number;
    chunk_status_breakdown: {
      pending: number;
      in_progress: number;
      done: number;
      abstained: number;
      failed: number;
    };
    last_activity_at: string | null;
    status: "ready" | "pending";
  };
  step2_visure_needed: {
    expected_document_types: string[];
    classified_document_types: string[];
    covered: string[];
    missing: string[];
    available_adapters: string[];
  };
  step3_visure_acquired: {
    count: number;
    items: { id: string; filename: string; source: string; ingestion_status: string }[];
  };
  step4_consolidation: {
    consolidated: boolean;
    consolidated_at: string | null;
  };
  preview_slots: PreviewSlots | null;
  can_execute: boolean;
  workflow_run_id: string | null;
};

export function ActPreparation({
  session,
  actId,
  onProceed,
}: {
  session: Session;
  actId: string;
  onProceed: () => void;
}) {
  const qc = useQueryClient();

  const prep = useQuery({
    queryKey: ["preparation", actId],
    queryFn: () =>
      apiFetch<PrepStatus>(`/v1/acts/${actId}/preparation`, {}, session.token),
    refetchInterval: pollWhile<PrepStatus>(
      (data) =>
        !data ||
        data.step1_catalog.status !== "ready" ||
        data.step3_visure_acquired.items.some((i) => i.ingestion_status !== "done"),
      3_000,
    ),
  });

  const consolidate = useMutation({
    mutationFn: () =>
      apiFetch(
        `/v1/acts/${actId}/preparation/consolidate`,
        { method: "POST" },
        session.token,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["preparation", actId] });
    },
  });

  const extractPreview = useMutation({
    mutationFn: () =>
      apiFetch<{ slots: Record<string, unknown>; abstained: string[] }>(
        `/v1/acts/${actId}/preparation/extract-preview`,
        { method: "POST" },
        session.token,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["preparation", actId] });
    },
  });

  // Auto-trigger preview quando il catalog e' ready e non c'e' ancora preview.
  // Eseguito una sola volta per ingresso pagina (mutate non scatena loop).
  const catalogReady = prep.data?.step1_catalog.status === "ready";
  const hasPreview = !!prep.data?.preview_slots;
  const allVisureClassified = prep.data?.step3_visure_acquired.items.every(
    (i) => i.ingestion_status === "done",
  ) ?? true;
  const consolidatedAlready = prep.data?.step4_consolidation.consolidated ?? false;
  useEffect(() => {
    if (
      catalogReady &&
      !hasPreview &&
      allVisureClassified &&
      !consolidatedAlready &&
      !extractPreview.isPending
    ) {
      extractPreview.mutate();
    }
    // intenzionale: vogliamo trigger UNA volta, quando catalogReady passa a true.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogReady, hasPreview, allVisureClassified, consolidatedAlready]);

  if (prep.isLoading) return <div style={{ padding: "1rem" }}>Carico stato...</div>;
  if (prep.isError) {
    return (
      <div style={{ padding: "1rem", background: "#fee2e2", color: "#7f1d1d", borderRadius: 4 }}>
        Errore: {String(prep.error)}
      </div>
    );
  }
  if (!prep.data) return null;

  const s = prep.data;
  const step1Done = s.step1_catalog.status === "ready";
  const step2Missing = s.step2_visure_needed.missing.length;
  const step3Done = s.step3_visure_acquired.items.every((i) => i.ingestion_status === "done");

  return (
    <div style={{ maxWidth: 1100 }}>
      {/* Status bar compatta in alto */}
      <PreparationStatusBar
        s={s}
        step1Done={step1Done}
        step2Missing={step2Missing}
        step3Done={step3Done}
        consolidate={consolidate}
        consolidatedAlready={consolidatedAlready}
        onProceed={onProceed}
        canExecute={s.can_execute}
      />

      {/* Workspace documenti: IN ALTO perche' e' il vero centro dell'azione */}
      <section style={{ marginTop: "1rem" }}>
        <DocumentsWorkspace
          session={session}
          actId={actId}
          selectedSource={null}
          onClearSelection={() => {}}
        />
      </section>

      {/* Dettagli step + acquire visure: collapsable sotto */}
      <details style={{ marginTop: "1.5rem" }} open={!consolidatedAlready}>
        <summary style={{ cursor: "pointer", fontWeight: 600, color: "#475569", padding: "0.4rem 0" }}>
          Dettagli dei passaggi di preparazione
        </summary>

      <StepCard
        n={1}
        title="Catalogo automatico dei documenti caricati"
        state={step1Done ? "done" : s.step1_catalog.documents_total === 0 ? "todo" : "in_progress"}
        body={
          s.step1_catalog.documents_total === 0 ? (
            <p style={{ margin: 0, color: "#475569" }}>
              <strong>Nessun documento caricato ancora.</strong> Trascina i file
              nel workspace qui sotto (o usa la "Demo guidata" gialla).
            </p>
          ) : (
            <>
              <Stat label="Documenti" v={`${s.step1_catalog.documents_classified} / ${s.step1_catalog.documents_total} classificati`} />
              <Stat label="Chunks" v={`${s.step1_catalog.chunks_classified} / ${s.step1_catalog.chunks_total} classificati`} />
              <Stat label="Tipi rilevati" v={s.step2_visure_needed.classified_document_types.join(", ") || "(nessuno)"} />
              <small style={{ color: "#64748b" }}>
                Parsing, chunking, embedding (bge-m3) + classificazione LLM (qwen2.5-7b).
                Automatico, ~30-70s per chunk.
              </small>
            </>
          )
        }
      />

      <StepCard
        n={2}
        title="Documenti previsti dal template"
        state={step2Missing === 0 && s.step2_visure_needed.expected_document_types.length > 0 ? "done" : "todo"}
        body={
          <>
            <p style={{ margin: "0 0 0.5rem", color: "#475569", fontSize: "0.9rem" }}>
              Il template <code>{s.template_id}</code> si aspetta questi tipi di documento:
            </p>
            <ul style={{ margin: "0 0 0.5rem", paddingLeft: "1.2rem" }}>
              {s.step2_visure_needed.expected_document_types.map((t) => (
                <li key={t} style={{ marginBottom: "0.25rem" }}>
                  {s.step2_visure_needed.covered.includes(t) ? (
                    <span style={{ color: "#16a34a" }}>✓ {t}</span>
                  ) : (
                    <span style={{ color: "#b91c1c" }}>✗ {t} (mancante)</span>
                  )}
                </li>
              ))}
              {s.step2_visure_needed.expected_document_types.length === 0 && (
                <li style={{ color: "#64748b" }}>(template senza extract_from)</li>
              )}
            </ul>
            {step2Missing > 0 && (
              <p style={{ margin: 0, color: "#92400e", fontSize: "0.85rem" }}>
                Puoi caricare manualmente i file mancanti (es. la visura
                ipocatastale fornita dal cliente), oppure acquisirla via
                adapter al passo successivo.
              </p>
            )}
          </>
        }
      />

      <StepCard
        n={3}
        title="Visure acquisite automaticamente"
        state={s.step3_visure_acquired.count > 0 && step3Done ? "done" : s.step3_visure_acquired.count > 0 ? "in_progress" : "todo"}
        body={
          <>
            <p style={{ margin: "0 0 0.5rem", color: "#475569", fontSize: "0.9rem" }}>
              Acquisizione tramite adapter mock (in Fase 5 saranno API reali
              SOGEI/Telemaco/ANPR). Ogni visura diventa un Document classificato
              e contribuisce all'estrazione slot.
            </p>
            <AcquireVisureBlock actId={actId} session={session} onDone={() => qc.invalidateQueries({ queryKey: ["preparation", actId] })} />
            {s.step3_visure_acquired.items.length > 0 && (
              <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
                {s.step3_visure_acquired.items.map((v) => (
                  <li key={v.id} style={{ fontSize: "0.85rem", marginBottom: "0.2rem" }}>
                    <code>{v.source}</code> — {v.filename}{" "}
                    <small style={{ color: "#64748b" }}>({v.ingestion_status})</small>
                  </li>
                ))}
              </ul>
            )}
          </>
        }
      />

      <SlotPreviewCard
        n={4}
        preview={s.preview_slots}
        loading={extractPreview.isPending}
        error={extractPreview.error ? String(extractPreview.error) : null}
        onRefresh={() => extractPreview.mutate()}
        catalogReady={step1Done}
      />

      <StepCard
        n={5}
        title="Consolida e procedi"
        state={s.step4_consolidation.consolidated ? "done" : "todo"}
        body={
          s.step4_consolidation.consolidated ? (
            <>
              <p style={{ margin: 0, color: "#14532d" }}>
                <strong>Consolidato</strong> il{" "}
                {new Date(s.step4_consolidation.consolidated_at!).toLocaleString("it-IT")}.
              </p>
              {s.can_execute && (
                <button
                  onClick={onProceed}
                  style={{
                    marginTop: "0.75rem",
                    padding: "0.7rem 1.4rem",
                    background: "#16a34a",
                    color: "white",
                    border: "none",
                    borderRadius: 4,
                    cursor: "pointer",
                    fontWeight: 700,
                    fontSize: "1rem",
                  }}
                >
                  ▶ Procedi alla generazione dell'atto
                </button>
              )}
              {s.workflow_run_id && (
                <p style={{ marginTop: "0.5rem", color: "#64748b", fontSize: "0.85rem" }}>
                  Workflow gia' avviato (run id <code>{s.workflow_run_id.slice(0, 8)}…</code>)
                </p>
              )}
            </>
          ) : (
            <>
              <p style={{ margin: "0 0 0.6rem", color: "#475569", fontSize: "0.9rem" }}>
                Quando i documenti sono tutti pronti, conferma il consolidamento.
                Questo sblocca il workflow di generazione atto + calcolo imposte +
                review.
              </p>
              <button
                onClick={() => consolidate.mutate()}
                disabled={!step1Done || consolidate.isPending}
                style={{
                  padding: "0.55rem 1.2rem",
                  background: step1Done ? "#1e293b" : "#cbd5e1",
                  color: "white",
                  border: "none",
                  borderRadius: 4,
                  cursor: step1Done ? "pointer" : "not-allowed",
                  fontWeight: 600,
                }}
              >
                {consolidate.isPending ? "..." : "✓ Consolida documenti"}
              </button>
              {!step1Done && (
                <small style={{ marginLeft: "0.6rem", color: "#92400e" }}>
                  Attendi il catalogo automatico (step 1) prima di consolidare.
                </small>
              )}
              {consolidate.isError && (
                <div style={{ marginTop: "0.5rem", color: "#b91c1c", fontSize: "0.85rem" }}>
                  {String(consolidate.error)}
                </div>
              )}
            </>
          )
        }
      />

      </details>
    </div>
  );
}

function PreparationStatusBar({
  s,
  step1Done,
  step2Missing,
  step3Done,
  consolidate,
  consolidatedAlready,
  onProceed,
  canExecute,
}: {
  s: PrepStatus;
  step1Done: boolean;
  step2Missing: number;
  step3Done: boolean;
  consolidate: { mutate: () => void; isPending: boolean };
  consolidatedAlready: boolean;
  onProceed: () => void;
  canExecute: boolean;
}) {
  const slotsCount = s.preview_slots ? Object.keys(s.preview_slots.slots).length : 0;
  const c = s.step1_catalog;
  const total = c.chunks_total;
  const done = c.chunk_status_breakdown?.done ?? c.chunks_classified;
  const inProgress = c.chunk_status_breakdown?.in_progress ?? 0;
  const abstained = c.chunk_status_breakdown?.abstained ?? 0;
  const failed = c.chunk_status_breakdown?.failed ?? 0;
  const pending = c.chunk_status_breakdown?.pending ?? Math.max(0, total - done - inProgress - abstained - failed);
  const pctDone = total > 0 ? Math.round((done * 100) / total) : 0;
  const pctAbst = total > 0 ? Math.round((abstained * 100) / total) : 0;
  const pctFail = total > 0 ? Math.round((failed * 100) / total) : 0;
  const showProgress = total > 0 && !step1Done;
  const heartbeat = useHeartbeatLabel(c.last_activity_at);
  const stepDot = (ok: boolean, n: number, label: string) => (
    <div style={{
      display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem",
      color: ok ? "#14532d" : "#64748b",
    }}>
      <span style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 22, height: 22, borderRadius: "50%",
        background: ok ? "#16a34a" : "#cbd5e1", color: "white",
        fontWeight: 700, fontSize: "0.78rem",
      }}>{ok ? "✓" : n}</span>
      {label}
    </div>
  );
  return (
    <section style={{
      background: "white", border: "1px solid #e2e8f0", borderRadius: 6,
      padding: "0.75rem 1rem",
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexWrap: "wrap", gap: "1rem",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
          {stepDot(step1Done, 1, `Catalogo (${s.step1_catalog.documents_classified}/${s.step1_catalog.documents_total} doc)`)}
          {stepDot(step2Missing === 0 && s.step2_visure_needed.expected_document_types.length > 0, 2, `Tipi previsti (${s.step2_visure_needed.covered.length}/${s.step2_visure_needed.expected_document_types.length})`)}
          {stepDot(s.step3_visure_acquired.count > 0 && step3Done, 3, `Visure auto (${s.step3_visure_acquired.count})`)}
          {stepDot(slotsCount > 0, 4, `Slot estratti (${slotsCount})`)}
          {stepDot(consolidatedAlready, 5, "Consolida")}
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          {!consolidatedAlready && (
            <button
              onClick={() => consolidate.mutate()}
              disabled={!step1Done || consolidate.isPending}
              style={{
                padding: "0.5rem 1rem",
                background: step1Done ? "#1e293b" : "#cbd5e1",
                color: "white", border: "none", borderRadius: 4,
                cursor: step1Done ? "pointer" : "not-allowed", fontWeight: 600,
                fontSize: "0.88rem",
              }}
            >
              {consolidate.isPending ? "..." : "✓ Consolida"}
            </button>
          )}
          {canExecute && (
            <button
              onClick={onProceed}
              style={{
                padding: "0.55rem 1.15rem",
                background: "#16a34a", color: "white",
                border: "none", borderRadius: 4, cursor: "pointer",
                fontWeight: 700, fontSize: "0.95rem",
              }}
            >
              ▶ Procedi alla generazione
            </button>
          )}
        </div>
      </div>

      {showProgress && (
        <div style={{ marginTop: "0.8rem" }}>
          <div style={{
            display: "flex", justifyContent: "space-between",
            fontSize: "0.78rem", color: "#475569", marginBottom: "0.3rem",
          }}>
            <span>
              Classificazione LLM in corso: <strong>{done}</strong>/{total} chunk pronti
              {inProgress > 0 && <span style={{ color: "#1e3a8a" }}> · {inProgress} in elaborazione</span>}
              {pending > 0 && <span style={{ color: "#64748b" }}> · {pending} in coda</span>}
              {abstained > 0 && <span style={{ color: "#92400e" }}> · {abstained} astenuti</span>}
              {failed > 0 && <span style={{ color: "#b91c1c" }}> · {failed} falliti</span>}
            </span>
            <span style={{ color: "#64748b" }}>
              Ultima attivita': <strong>{heartbeat}</strong>
            </span>
          </div>
          <div style={{
            position: "relative", height: 14, background: "#e2e8f0",
            borderRadius: 7, overflow: "hidden", display: "flex",
          }}>
            <div title={`done ${pctDone}%`} style={{ width: `${pctDone}%`, background: "#16a34a" }} />
            <div title={`abstained ${pctAbst}%`} style={{ width: `${pctAbst}%`, background: "#f59e0b" }} />
            <div title={`failed ${pctFail}%`} style={{ width: `${pctFail}%`, background: "#dc2626" }} />
            {inProgress > 0 && (
              <div
                style={{
                  width: `${Math.round((inProgress * 100) / total)}%`,
                  background: "repeating-linear-gradient(45deg,#93c5fd,#93c5fd 6px,#bfdbfe 6px,#bfdbfe 12px)",
                  animation: "notai-pulse 1.5s linear infinite",
                }}
              />
            )}
          </div>
          <style>{`
            @keyframes notai-pulse {
              0% { opacity: 0.85 }
              50% { opacity: 1 }
              100% { opacity: 0.85 }
            }
          `}</style>
        </div>
      )}
    </section>
  );
}

function useHeartbeatLabel(iso: string | null): string {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!iso) return "(nessuna)";
  const t = Date.parse(iso);
  if (isNaN(t)) return "(?)";
  const sec = Math.max(0, Math.round((now - t) / 1000));
  if (sec < 60) return `${sec}s fa`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s fa`;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return `${h}h ${m}m fa`;
}

function SlotPreviewCard({
  n,
  preview,
  loading,
  error,
  onRefresh,
  catalogReady,
}: {
  n: number;
  preview: PreviewSlots | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  catalogReady: boolean;
}) {
  const state = !catalogReady
    ? "todo"
    : loading
    ? "in_progress"
    : preview && Object.keys(preview.slots).length > 0
    ? "done"
    : "todo";

  return (
    <StepCard
      n={n}
      title="Anteprima dati estratti dai documenti"
      state={state}
      body={
        <>
          <p style={{ margin: "0 0 0.6rem", color: "#475569", fontSize: "0.9rem" }}>
            NotAI legge i documenti classificati e ricava i valori del template
            (indirizzo immobile, foglio, particella, prezzo, provenienza, ...).
            Ogni valore e' <strong>grounded</strong> su un chunk specifico,
            altrimenti il sistema si astiene (zero-allucinazione).
          </p>
          {!catalogReady && (
            <p style={{ margin: 0, color: "#92400e", fontSize: "0.85rem" }}>
              Attendi che il catalogo automatico (step 1) sia completo.
            </p>
          )}
          {catalogReady && loading && (
            <p style={{ margin: 0, color: "#1e3a8a", fontSize: "0.88rem" }}>
              Estraggo dai documenti via LLM locale... (~30-90s)
            </p>
          )}
          {error && (
            <div style={{ color: "#b91c1c", fontSize: "0.85rem", marginBottom: "0.5rem" }}>
              {error}
            </div>
          )}
          {preview && (
            <>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.86rem", marginTop: "0.4rem" }}>
                <thead>
                  <tr>
                    <th style={{ ...thStyle, width: "30%" }}>Slot</th>
                    <th style={thStyle}>Valore estratto</th>
                    <th style={{ ...thStyle, width: 80 }}>Conf</th>
                    <th style={{ ...thStyle, width: 140 }}>Sorgente</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(preview.slots).map(([name, value]) => {
                    const prov = preview.provenance[name];
                    return (
                      <tr key={name}>
                        <td style={tdStyle}><code style={codeStyle}>{name}</code></td>
                        <td style={tdStyle}><strong>{formatVal(value)}</strong></td>
                        <td style={tdStyle}>{prov ? `${(prov.confidence * 100).toFixed(0)}%` : "—"}</td>
                        <td style={tdStyle}>
                          {prov?.chunk_id ? (
                            <code style={{ ...codeStyle, fontSize: "0.7rem" }} title={`chunk ${prov.chunk_id}`}>
                              {prov.chunk_id.slice(0, 8)}…
                            </code>
                          ) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                  {preview.abstained.map((name) => (
                    <tr key={name} style={{ background: "#fef2f2" }}>
                      <td style={tdStyle}><code style={codeStyle}>{name}</code></td>
                      <td style={{ ...tdStyle, color: "#b91c1c", fontStyle: "italic" }}>
                        astenuto (non groundable)
                      </td>
                      <td style={tdStyle} colSpan={2}>—</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ marginTop: "0.6rem", fontSize: "0.78rem", color: "#64748b" }}>
                Estratto il {new Date(preview.extracted_at).toLocaleString("it-IT")}.{" "}
                <button
                  onClick={onRefresh}
                  disabled={loading}
                  style={{
                    padding: "0.2rem 0.6rem",
                    background: "white",
                    border: "1px solid #cbd5e1",
                    borderRadius: 3,
                    cursor: loading ? "wait" : "pointer",
                    fontSize: "0.78rem",
                    marginLeft: "0.4rem",
                  }}
                >
                  ↻ Ri-estrai
                </button>
              </div>
            </>
          )}
          {catalogReady && !preview && !loading && !error && (
            <button
              onClick={onRefresh}
              style={{
                marginTop: "0.5rem",
                padding: "0.5rem 1rem",
                background: "#1e293b",
                color: "white",
                border: "none",
                borderRadius: 4,
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              Estrai slot dai documenti
            </button>
          )}
        </>
      }
    />
  );
}

function formatVal(v: string | number | boolean | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toLocaleString("it-IT");
  if (typeof v === "boolean") return v ? "si" : "no";
  return String(v);
}

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.35rem 0.4rem",
  borderBottom: "1px solid #cbd5e1",
  fontSize: "0.78rem",
  color: "#64748b",
  textTransform: "uppercase",
  letterSpacing: 0.4,
};
const tdStyle: React.CSSProperties = {
  padding: "0.35rem 0.4rem",
  borderBottom: "1px solid #e2e8f0",
  verticalAlign: "top",
};
const codeStyle: React.CSSProperties = {
  background: "#f1f5f9",
  padding: "0.05rem 0.35rem",
  borderRadius: 3,
  fontFamily: "ui-monospace, Menlo, monospace",
  fontSize: "0.78rem",
};


function AcquireVisureBlock({
  actId,
  session,
  onDone,
}: {
  actId: string;
  session: Session;
  onDone: () => void;
}) {
  const [adapter, setAdapter] = useState<"telemaco" | "anpr">("anpr");
  const [key, setKey] = useState("RSSMRA70A01F205X");

  const fetcher = useMutation({
    mutationFn: () =>
      apiFetch(
        `/v1/acts/${actId}/preparation/acquire-visure`,
        {
          method: "POST",
          body: JSON.stringify({
            adapter,
            party_fiscal_code: adapter === "anpr" ? key : null,
            party_vat: adapter === "telemaco" ? key : null,
          }),
        },
        session.token,
      ),
    onSuccess: () => onDone(),
  });

  return (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
      <select value={adapter} onChange={(e) => setAdapter(e.target.value as "telemaco" | "anpr")} style={inputStyle}>
        <option value="anpr">ANPR (persona fisica)</option>
        <option value="telemaco">Telemaco (persona giuridica)</option>
      </select>
      <input
        value={key}
        onChange={(e) => setKey(e.target.value)}
        placeholder={adapter === "anpr" ? "Codice fiscale" : "P.IVA"}
        style={{ ...inputStyle, flex: 1, minWidth: 200 }}
      />
      <button
        onClick={() => fetcher.mutate()}
        disabled={fetcher.isPending || !key.trim()}
        style={{
          padding: "0.4rem 0.9rem",
          background: "#1e293b",
          color: "white",
          border: "none",
          borderRadius: 4,
          cursor: "pointer",
          fontWeight: 600,
          fontSize: "0.88rem",
        }}
      >
        {fetcher.isPending ? "..." : "+ Acquisisci"}
      </button>
      {fetcher.isError && (
        <div style={{ color: "#b91c1c", fontSize: "0.82rem", width: "100%" }}>
          {String(fetcher.error)}
        </div>
      )}
    </div>
  );
}

function StepCard({
  n,
  title,
  state,
  body,
}: {
  n: number;
  title: string;
  state: "todo" | "in_progress" | "done";
  body: React.ReactNode;
}) {
  const palette = {
    todo: { bg: "#f8fafc", border: "#cbd5e1", chip: "#94a3b8" },
    in_progress: { bg: "#fefce8", border: "#eab308", chip: "#a16207" },
    done: { bg: "#dcfce7", border: "#16a34a", chip: "#15803d" },
  }[state];
  return (
    <section style={{
      background: palette.bg,
      borderLeft: `4px solid ${palette.border}`,
      borderRadius: 4,
      padding: "0.9rem 1.2rem",
      marginBottom: "0.8rem",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
        <span style={{
          width: 26, height: 26, borderRadius: "50%",
          background: palette.chip, color: "white",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontWeight: 700, fontSize: "0.85rem",
        }}>
          {state === "done" ? "✓" : n}
        </span>
        <h3 style={{ margin: 0, fontSize: "1rem" }}>{title}</h3>
      </div>
      <div style={{ paddingLeft: "2rem" }}>{body}</div>
    </section>
  );
}

function Stat({ label, v }: { label: string; v: string }) {
  return (
    <div style={{ display: "flex", gap: "0.6rem", fontSize: "0.88rem", padding: "0.15rem 0" }}>
      <strong style={{ color: "#475569", minWidth: 110 }}>{label}:</strong>
      <span style={{ color: "#0f172a" }}>{v}</span>
    </div>
  );
}

import type React from "react";

const inputStyle: React.CSSProperties = {
  padding: "0.4rem 0.6rem",
  border: "1px solid #cbd5e1",
  borderRadius: 4,
  fontSize: "0.88rem",
  background: "white",
};
