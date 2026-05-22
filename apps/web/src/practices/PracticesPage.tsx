// Pagina Pratiche: lista + crea + drill-down al dettaglio.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, type Session } from "../auth";
import { buildHref, type Route, type Tab } from "../routing";
import { PracticeDetail } from "./PracticeDetail";

type Practice = {
  id: string;
  tenant_id: string;
  code: string;
  kind: string;
  title: string;
  description: string | null;
  status: string;
  responsible_user_id: string | null;
  created_at: string;
  updated_at: string;
};

const PRACTICE_KINDS = [
  "notarile.compravendita.immobiliare",
  "notarile.mutuo",
  "notarile.donazione",
  "notarile.successione",
  "notarile.costituzione_srl",
  "notarile.verbale_assemblea",
  "legale.civile.contenzioso",
  "legale.recupero_crediti",
];

export function PracticesPage({
  session,
  onNeedLogin,
  route,
  goto,
}: {
  session: Session | null;
  onNeedLogin: () => void;
  route: Route;
  goto: (tab: Tab, opts?: { practiceId?: string; actId?: string }) => void;
}) {
  if (!session) {
    return (
      <div style={s.empty}>
        <h2>Accedi per gestire le pratiche</h2>
        <button onClick={onNeedLogin} style={s.bigLogin}>Accedi (dev) ora</button>
      </div>
    );
  }

  if (route.practiceId) {
    return (
      <PracticeDetail
        session={session}
        practiceId={route.practiceId}
        actId={route.actId}
        goto={goto}
      />
    );
  }

  return <PracticesList session={session} goto={goto} />;
}

function PracticesList({
  session,
  goto,
}: {
  session: Session;
  goto: (tab: Tab, opts?: { practiceId?: string; actId?: string }) => void;
}) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    code: `2026/${String(Math.floor(Math.random() * 9999)).padStart(4, "0")}`,
    kind: PRACTICE_KINDS[0],
    title: "",
    description: "",
  });

  const list = useQuery({
    queryKey: ["practices", session.token],
    queryFn: () => apiFetch<Practice[]>("/v1/practices", {}, session.token),
  });

  const create = useMutation({
    mutationFn: (body: typeof form) =>
      apiFetch<Practice>("/v1/practices", { method: "POST", body: JSON.stringify(body) }, session.token),
    onSuccess: (created) => {
      setShowForm(false);
      setForm({ ...form, title: "", description: "" });
      qc.invalidateQueries({ queryKey: ["practices", session.token] });
      goto("practices", { practiceId: created.id });
    },
  });

  return (
    <div>
      <div style={s.header}>
        <h1 style={{ margin: 0 }}>Pratiche</h1>
        <button onClick={() => setShowForm((v) => !v)} style={s.primaryBtn}>
          {showForm ? "Annulla" : "+ Nuova pratica"}
        </button>
      </div>
      <p style={s.help}>Le pratiche (fascicoli) raggruppano gli atti relativi a un cliente o operazione.</p>

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (form.title.trim()) create.mutate(form);
          }}
          style={s.formCard}
        >
          <div style={s.formGrid}>
            <Field label="Codice pratica">
              <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} style={s.input} required />
            </Field>
            <Field label="Tipo">
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} style={s.input}>
                {PRACTICE_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </Field>
            <Field label="Titolo">
              <input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="es. Rossi - Bianchi compravendita appartamento Milano"
                style={s.input}
                required
              />
            </Field>
            <Field label="Descrizione (opzionale)" full>
              <textarea
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                style={{ ...s.input, minHeight: 60, resize: "vertical" }}
              />
            </Field>
          </div>
          <button type="submit" disabled={create.isPending} style={s.primaryBtn}>
            {create.isPending ? "Creo..." : "Crea pratica"}
          </button>
          {create.isError && <div style={s.error}>{String(create.error)}</div>}
        </form>
      )}

      {list.isLoading && <p>Carico...</p>}
      {list.isError && <div style={s.error}>{String(list.error)}</div>}
      {list.data && list.data.length === 0 && (
        <div style={s.emptyList}>
          Nessuna pratica ancora. Crea la prima con il button qui sopra.
        </div>
      )}

      {list.data && list.data.length > 0 && (
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>Codice</th>
              <th style={s.th}>Titolo</th>
              <th style={s.th}>Tipo</th>
              <th style={s.th}>Stato</th>
              <th style={s.th}>Creata</th>
            </tr>
          </thead>
          <tbody>
            {list.data.map((p) => (
              <tr key={p.id} style={s.tr} onClick={() => goto("practices", { practiceId: p.id })}>
                <td style={s.td}><code>{p.code}</code></td>
                <td style={s.td}>{p.title}</td>
                <td style={s.td}><code style={s.kindBadge}>{p.kind}</code></td>
                <td style={s.td}><span style={s.statusBadge}>{p.status}</span></td>
                <td style={s.td}>{new Date(p.created_at).toLocaleString("it-IT")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <label style={{ ...s.field, gridColumn: full ? "1 / -1" : undefined }}>
      <span style={s.fieldLabel}>{label}</span>
      {children}
    </label>
  );
}

export const s = {
  empty: { textAlign: "center", padding: "3rem 1rem", color: "#475569" } as React.CSSProperties,
  bigLogin: {
    marginTop: "1rem",
    padding: "0.8rem 2rem",
    background: "#16a34a",
    color: "white",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontWeight: 700,
  } as React.CSSProperties,
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" } as React.CSSProperties,
  help: { color: "#64748b", marginBottom: "1.5rem" } as React.CSSProperties,
  primaryBtn: {
    padding: "0.5rem 1.1rem",
    background: "#1e293b",
    color: "white",
    border: "none",
    borderRadius: 4,
    cursor: "pointer",
    fontWeight: 600,
  } as React.CSSProperties,
  secondaryBtn: {
    padding: "0.5rem 1.1rem",
    background: "white",
    color: "#1e293b",
    border: "1px solid #cbd5e1",
    borderRadius: 4,
    cursor: "pointer",
  } as React.CSSProperties,
  formCard: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 6,
    padding: "1rem 1.25rem",
    marginBottom: "1.5rem",
  } as React.CSSProperties,
  formGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: "0.75rem",
    marginBottom: "1rem",
  } as React.CSSProperties,
  field: { display: "flex", flexDirection: "column", gap: "0.25rem" } as React.CSSProperties,
  fieldLabel: { fontSize: "0.8rem", color: "#475569", fontWeight: 600 } as React.CSSProperties,
  input: {
    padding: "0.45rem 0.6rem",
    border: "1px solid #cbd5e1",
    borderRadius: 4,
    fontSize: "0.92rem",
    background: "white",
    fontFamily: "inherit",
  } as React.CSSProperties,
  error: {
    marginTop: "0.6rem",
    background: "#fee2e2",
    color: "#7f1d1d",
    padding: "0.5rem 0.75rem",
    borderRadius: 4,
    fontSize: "0.85rem",
  } as React.CSSProperties,
  emptyList: { padding: "2rem", textAlign: "center", color: "#94a3b8" } as React.CSSProperties,
  table: { width: "100%", borderCollapse: "collapse", background: "white" } as React.CSSProperties,
  th: {
    textAlign: "left",
    padding: "0.6rem 0.75rem",
    borderBottom: "2px solid #cbd5e1",
    fontSize: "0.85rem",
    color: "#475569",
  } as React.CSSProperties,
  tr: { cursor: "pointer" } as React.CSSProperties,
  td: {
    padding: "0.6rem 0.75rem",
    borderBottom: "1px solid #e2e8f0",
    fontSize: "0.9rem",
  } as React.CSSProperties,
  kindBadge: {
    fontSize: "0.78rem",
    background: "#f1f5f9",
    padding: "0.1rem 0.4rem",
    borderRadius: 3,
  } as React.CSSProperties,
  statusBadge: {
    fontSize: "0.78rem",
    padding: "0.15rem 0.5rem",
    background: "#fef3c7",
    color: "#78350f",
    borderRadius: 999,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  } as React.CSSProperties,
};
