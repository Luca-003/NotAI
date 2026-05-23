// Dettaglio pratica: info + lista atti + crea atto + drill-down workflow.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, type Session } from "../auth";
import { ActPage } from "../acts/ActPage";
import { Breadcrumb } from "../components/Breadcrumb";
import { buildHref, type Tab } from "../routing";
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
  actId,
  goto,
}: {
  session: Session;
  practiceId: string;
  actId: string | null;
  goto: (tab: Tab, opts?: { practiceId?: string; actId?: string }) => void;
}) {
  const practice = useQuery({
    queryKey: ["practice", practiceId],
    queryFn: () => apiFetch<Practice>(`/v1/practices/${practiceId}`, {}, session.token),
  });

  if (actId) {
    return (
      <ActPage
        session={session}
        actId={actId}
        practiceTitle={practice.data?.title ?? "Pratica"}
        practiceId={practiceId}
        goto={goto}
      />
    );
  }

  return (
    <div>
      <Breadcrumb
        crumbs={[
          { label: "Pratiche", href: buildHref("practices") },
          { label: practice.data?.title ?? "Pratica..." },
        ]}
      />

      {practice.isLoading && <p style={{ marginTop: "1rem" }}>Carico...</p>}
      {practice.isError && <div style={s.error}>{String(practice.error)}</div>}

      {practice.data && (
        <>
          <header style={{ marginBottom: "1.5rem" }}>
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

          <ActsSection session={session} practiceId={practiceId} goto={goto} />
        </>
      )}
    </div>
  );
}

function ActsSection({
  session,
  practiceId,
  goto,
}: {
  session: Session;
  practiceId: string;
  goto: (tab: Tab, opts?: { practiceId?: string; actId?: string }) => void;
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
      goto("practices", { practiceId, actId: act.id });
    },
  });

  const hasActs = !!(acts.data && acts.data.length > 0);

  return (
    <section
      style={{
        background: "white",
        border: hasActs ? "1px solid #e2e8f0" : "2px dashed #cbd5e1",
        borderRadius: 6,
        padding: "1rem 1.25rem",
      }}
    >
      <div style={s.header}>
        <h2 style={{ margin: 0, fontSize: "1.15rem" }}>
          {hasActs ? `Atti della pratica (${acts.data!.length})` : "Atti"}
        </h2>
        <button onClick={() => setShowForm((v) => !v)} style={s.primaryBtn}>
          {showForm ? "Annulla" : "+ Nuovo atto"}
        </button>
      </div>

      {!hasActs && !showForm && (
        <div style={{ marginTop: "1rem", color: "#475569" }}>
          <p style={{ marginTop: 0 }}>
            <strong>Questa pratica non ha ancora atti.</strong>
          </p>
          <p style={{ fontSize: "0.9rem" }}>
            Un atto e' il documento giuridico principale (compravendita, mutuo,
            donazione, atto di citazione...). Sotto l'atto si caricano i
            documenti di input e si avvia il workflow.
          </p>
          <button onClick={() => setShowForm(true)} style={{ ...s.primaryBtn, marginTop: "0.5rem" }}>
            Crea il primo atto
          </button>
        </div>
      )}

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

      {hasActs && (
        <ul style={{ listStyle: "none", padding: 0, marginTop: "1rem" }}>
          {acts.data!.map((a) => (
            <li
              key={a.id}
              onClick={() => goto("practices", { practiceId, actId: a.id })}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#f8fafc")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "white")}
              style={{
                padding: "0.75rem 1rem",
                border: "1px solid #e2e8f0",
                borderRadius: 4,
                marginBottom: "0.5rem",
                cursor: "pointer",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "white",
                transition: "background 100ms",
              }}
              title="Click per aprire l'atto"
            >
              <div>
                <strong style={{ color: "#0f172a" }}>{a.title}</strong>{" "}
                <code style={{ ...s.kindBadge, marginLeft: "0.5rem" }}>{a.kind}</code>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                <span style={s.statusBadge}>{a.workflow_status}</span>
                <span style={{ color: "#94a3b8", fontWeight: 700 }}>›</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
