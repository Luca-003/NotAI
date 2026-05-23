// ActPreparation: vista dell'atto PRIMA del workflow Temporal.
// Articola in 4 step espliciti la fase di consolidamento documenti:
//   1. Catalogo  (automatico: ingestion + classify)
//   2. Visure needed (cosa il template chiede e non e' presente)
//   3. Visure acquisite (mock adapter -> Document)
//   4. Consolida (notaio approva, sblocca workflow)

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, type Session } from "../auth";
import { DocumentsWorkspace } from "./DocumentsWorkspace";
import { pollWhile } from "../hooks/polling";

type PrepStatus = {
  act_id: string;
  template_id: string;
  template_known: boolean;
  step1_catalog: {
    documents_total: number;
    documents_classified: number;
    chunks_total: number;
    chunks_classified: number;
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
      <h2 style={{ marginTop: 0 }}>Preparazione atto</h2>
      <p style={{ color: "#475569", fontSize: "0.92rem", marginTop: 0 }}>
        Prima di generare la bozza, NotAI deve aver catalogato tutti i documenti
        di input e acquisito le visure necessarie dal template. Al termine,
        clicca <strong>"Procedi alla generazione"</strong> per avviare il
        workflow di redazione.
      </p>

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

      <StepCard
        n={4}
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

      <h3 style={{ marginTop: "2rem" }}>Workspace documenti</h3>
      <DocumentsWorkspace
        session={session}
        actId={actId}
        selectedSource={null}
        onClearSelection={() => {}}
      />
    </div>
  );
}

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
