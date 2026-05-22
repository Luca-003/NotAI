// Dettaglio pratica: info + lista atti + crea atto + drill-down workflow.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, type Session } from "../auth";
import { ActDetail } from "../acts/ActDetail";
import { s } from "./PracticesPage";

type Practice = {
  id: string;
  code: string;
  kind: string;
  title: string;
  description: string | null;
  status: string;
  created_at: string;
};

type Act = {
  id: string;
  practice_id: string;
  kind: string;
  title: string;
  workflow_status: string;
  workflow_run_id: string | null;
};

const ACT_KINDS = [
  "notarile.compravendita.immobiliare",
  "notarile.mutuo",
  "notarile.donazione",
  "notarile.verbale",
  "legale.atto_citazione",
  "legale.ricorso",
];

export function PracticeDetail({
  session,
  practiceId,
  onBack,
}: {
  session: Session;
  practiceId: string;
  onBack: () => void;
}) {
  const [selectedActId, setSelectedActId] = useState<string | null>(null);

  const practice = useQuery({
    queryKey: ["practice", practiceId],
    queryFn: () => apiFetch<Practice>(`/v1/practices/${practiceId}`, {}, session.token),
  });

  if (selectedActId) {
    return (
      <ActDetail
        session={session}
        actId={selectedActId}
        onBack={() => setSelectedActId(null)}
      />
    );
  }

  return (
    <div>
      <button onClick={onBack} style={s.secondaryBtn}>← Pratiche</button>

      {practice.isLoading && <p style={{ marginTop: "1rem" }}>Carico...</p>}
      {practice.isError && <div style={s.error}>{String(practice.error)}</div>}

      {practice.data && (
        <>
          <header style={{ marginTop: "1rem", marginBottom: "1.5rem" }}>
            <h1 style={{ margin: 0 }}>{practice.data.title}</h1>
            <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
              <code style={s.kindBadge}>{practice.data.code}</code>
              <code style={s.kindBadge}>{practice.data.kind}</code>
              <span style={s.statusBadge}>{practice.data.status}</span>
              <span style={{ color: "#94a3b8", fontSize: "0.85rem" }}>
                creata il {new Date(practice.data.created_at).toLocaleString("it-IT")}
              </span>
            </div>
            {practice.data.description && (
              <p style={{ marginTop: "0.75rem", color: "#475569" }}>{practice.data.description}</p>
            )}
          </header>

          <ActsSection session={session} practiceId={practiceId} onOpenAct={setSelectedActId} />
        </>
      )}
    </div>
  );
}

function ActsSection({
  session,
  practiceId,
  onOpenAct,
}: {
  session: Session;
  practiceId: string;
  onOpenAct: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ kind: ACT_KINDS[0], title: "" });

  const acts = useQuery({
    queryKey: ["acts-of", practiceId],
    queryFn: () =>
      apiFetch<Act[]>(`/v1/practices/${practiceId}/acts`, {}, session.token),
  });

  const create = useMutation({
    mutationFn: (body: { kind: string; title: string }) =>
      apiFetch<Act>(
        "/v1/acts",
        { method: "POST", body: JSON.stringify({ ...body, practice_id: practiceId }) },
        session.token,
      ),
    onSuccess: (act) => {
      setShowForm(false);
      setForm({ ...form, title: "" });
      qc.invalidateQueries({ queryKey: ["acts-of", practiceId] });
      qc.setQueryData<Act[]>(["acts-of", practiceId], (old) => [...(old ?? []), act]);
      onOpenAct(act.id);
    },
  });

  return (
    <section style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 6, padding: "1rem 1.25rem" }}>
      <div style={s.header}>
        <h2 style={{ margin: 0, fontSize: "1.15rem" }}>Atti</h2>
        <button onClick={() => setShowForm((v) => !v)} style={s.primaryBtn}>
          {showForm ? "Annulla" : "+ Nuovo atto"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (form.title.trim()) create.mutate(form);
          }}
          style={{ marginTop: "1rem", padding: "1rem", background: "#f8fafc", borderRadius: 4 }}
        >
          <div style={s.formGrid}>
            <label style={s.field}>
              <span style={s.fieldLabel}>Tipo atto</span>
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} style={s.input}>
                {ACT_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            <label style={s.field}>
              <span style={s.fieldLabel}>Titolo</span>
              <input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="es. Compravendita appartamento via Roma"
                style={s.input}
                required
              />
            </label>
          </div>
          <button type="submit" disabled={create.isPending} style={s.primaryBtn}>
            {create.isPending ? "Creo..." : "Crea atto e apri"}
          </button>
          {create.isError && <div style={s.error}>{String(create.error)}</div>}
        </form>
      )}

      {acts.data && acts.data.length === 0 && (
        <div style={s.emptyList}>
          Nessun atto in questa pratica. Crea il primo con "+ Nuovo atto".
        </div>
      )}
      {acts.data && acts.data.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, marginTop: "1rem" }}>
          {acts.data.map((a) => (
            <li
              key={a.id}
              onClick={() => onOpenAct(a.id)}
              style={{
                padding: "0.6rem 0.75rem",
                border: "1px solid #e2e8f0",
                borderRadius: 4,
                marginBottom: "0.4rem",
                cursor: "pointer",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <strong>{a.title}</strong>{" "}
                <code style={{ ...s.kindBadge, marginLeft: "0.5rem" }}>{a.kind}</code>
              </div>
              <span style={s.statusBadge}>{a.workflow_status}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
