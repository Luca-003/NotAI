// Pagina admin per attivare/disattivare i moduli del tenant corrente.
//
// In Fase 4 il token JWT non e' ancora gestito dal frontend (bootstrap via curl
// genera token che l'utente puo' incollare); la pagina prevede un input "token"
// che viene memorizzato in localStorage e usato per le call API.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

type ModuleStatus = {
  id: string;
  name: string;
  category: string;
  description: string;
  requires: string[];
  essential: boolean;
  default_enabled: boolean;
  tags: string[];
  enabled: boolean;
  source: "tenant-override" | "default";
  note: string | null;
  changed_at: string | null;
  changed_by: string | null;
};

type ModulesResponse = { modules: ModuleStatus[]; count: number };

const TOKEN_KEY = "notai.jwt";

async function authedFetch(path: string, init: RequestInit = {}, token: string) {
  const r = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init.headers || {}),
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text().catch(() => "")}`);
  return r.json();
}

export function ModulesPage() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? "");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const qc = useQueryClient();

  useEffect(() => {
    if (token) localStorage.setItem(TOKEN_KEY, token);
  }, [token]);

  const modules = useQuery({
    queryKey: ["modules", token],
    queryFn: () => authedFetch("/v1/modules", {}, token) as Promise<ModulesResponse>,
    enabled: token.length > 10,
  });

  const toggle = useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) =>
      authedFetch(
        `/v1/modules/${id}`,
        { method: "PUT", body: JSON.stringify({ enabled }) },
        token,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modules", token] }),
  });

  const categories = Array.from(new Set((modules.data?.modules ?? []).map((m) => m.category)));
  const filtered = (modules.data?.modules ?? []).filter(
    (m) => categoryFilter === "all" || m.category === categoryFilter,
  );

  return (
    <div style={{ maxWidth: 980 }}>
      <h1 style={{ marginBottom: "0.5rem" }}>Moduli</h1>
      <p style={{ color: "#64748b", marginBottom: "1.5rem" }}>
        Attiva o disattiva le funzionalita' del sistema per il tuo studio. I moduli{" "}
        <strong>essenziali</strong> (core.*) sono sempre attivi e non disattivabili.
      </p>

      <section style={styles.tokenBox}>
        <label style={styles.tokenLabel}>JWT token (incolla dopo bootstrap dev):</label>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="eyJhbGciOiJIUzI1NiI..."
          style={styles.tokenInput}
        />
      </section>

      {!token && (
        <div style={styles.hint}>
          Per usare questa pagina serve un JWT. In dev: <code>POST /api/v1/dev/bootstrap</code>.
        </div>
      )}

      {modules.isError && (
        <div style={styles.error}>Errore: {String(modules.error)}</div>
      )}

      {modules.data && (
        <>
          <div style={styles.filterBar}>
            <button
              onClick={() => setCategoryFilter("all")}
              style={{
                ...styles.filterBtn,
                ...(categoryFilter === "all" ? styles.filterBtnActive : {}),
              }}
            >
              Tutti ({modules.data.count})
            </button>
            {categories.map((c) => (
              <button
                key={c}
                onClick={() => setCategoryFilter(c)}
                style={{
                  ...styles.filterBtn,
                  ...(categoryFilter === c ? styles.filterBtnActive : {}),
                }}
              >
                {c}
              </button>
            ))}
          </div>

          <div style={styles.grid}>
            {filtered.map((m) => (
              <article key={m.id} style={styles.card}>
                <header style={styles.cardHeader}>
                  <div>
                    <h3 style={styles.cardTitle}>{m.name}</h3>
                    <code style={styles.moduleId}>{m.id}</code>
                  </div>
                  <ToggleSwitch
                    checked={m.enabled}
                    disabled={m.essential || toggle.isPending}
                    onChange={(next) => toggle.mutate({ id: m.id, enabled: next })}
                  />
                </header>
                <p style={styles.cardDesc}>{m.description}</p>
                <div style={styles.metaRow}>
                  {m.essential && <span style={styles.badge}>essenziale</span>}
                  {m.tags.includes("planned") && (
                    <span style={{ ...styles.badge, background: "#fde68a", color: "#78350f" }}>
                      planned
                    </span>
                  )}
                  {m.tags.includes("ai-act-high-risk") && (
                    <span style={{ ...styles.badge, background: "#fecaca", color: "#7f1d1d" }}>
                      AI Act high-risk
                    </span>
                  )}
                  {m.source === "tenant-override" && (
                    <span style={{ ...styles.badge, background: "#dbeafe", color: "#1e40af" }}>
                      override
                    </span>
                  )}
                  {m.requires.length > 0 && (
                    <span style={styles.requires}>
                      richiede: {m.requires.map((r) => <code key={r}>{r}</code>).reduce<React.ReactNode[]>(
                        (acc, el, i) => (i ? [...acc, ", ", el] : [el]),
                        [],
                      )}
                    </span>
                  )}
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ToggleSwitch({
  checked,
  disabled,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      aria-pressed={checked}
      style={{
        width: 44,
        height: 24,
        borderRadius: 12,
        border: "none",
        background: checked ? "#16a34a" : "#cbd5e1",
        cursor: disabled ? "not-allowed" : "pointer",
        position: "relative",
        opacity: disabled ? 0.6 : 1,
        flexShrink: 0,
      }}
      title={disabled ? "Modulo essenziale (non disattivabile)" : ""}
    >
      <span
        style={{
          position: "absolute",
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: "white",
          top: 3,
          left: checked ? 23 : 3,
          transition: "left 120ms",
        }}
      />
    </button>
  );
}

const styles = {
  tokenBox: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 6,
    padding: "0.75rem",
    marginBottom: "1.5rem",
  } as React.CSSProperties,
  tokenLabel: { display: "block", fontSize: "0.85rem", color: "#475569", marginBottom: "0.25rem" },
  tokenInput: {
    width: "100%",
    padding: "0.4rem 0.6rem",
    fontFamily: "ui-monospace, Menlo, Consolas, monospace",
    fontSize: "0.85rem",
    border: "1px solid #cbd5e1",
    borderRadius: 4,
  } as React.CSSProperties,
  hint: {
    background: "#fffbeb",
    border: "1px solid #fcd34d",
    color: "#78350f",
    padding: "0.6rem",
    borderRadius: 4,
    marginBottom: "1rem",
  } as React.CSSProperties,
  error: {
    background: "#fee2e2",
    border: "1px solid #f87171",
    color: "#7f1d1d",
    padding: "0.6rem",
    borderRadius: 4,
    marginBottom: "1rem",
  } as React.CSSProperties,
  filterBar: { display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" } as React.CSSProperties,
  filterBtn: {
    padding: "0.35rem 0.75rem",
    border: "1px solid #cbd5e1",
    background: "white",
    borderRadius: 999,
    fontSize: "0.85rem",
    cursor: "pointer",
  } as React.CSSProperties,
  filterBtnActive: { background: "#1e293b", color: "white", borderColor: "#1e293b" } as React.CSSProperties,
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))",
    gap: "1rem",
  } as React.CSSProperties,
  card: {
    border: "1px solid #e2e8f0",
    borderRadius: 6,
    padding: "1rem",
    background: "white",
  } as React.CSSProperties,
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: "1rem",
    marginBottom: "0.5rem",
  } as React.CSSProperties,
  cardTitle: { margin: 0, fontSize: "1.05rem", color: "#0f172a" } as React.CSSProperties,
  moduleId: { fontSize: "0.75rem", color: "#64748b" } as React.CSSProperties,
  cardDesc: { color: "#334155", fontSize: "0.9rem", lineHeight: 1.5, margin: "0.5rem 0" },
  metaRow: { display: "flex", flexWrap: "wrap", gap: "0.4rem", alignItems: "center", fontSize: "0.78rem" } as React.CSSProperties,
  badge: {
    background: "#f1f5f9",
    color: "#475569",
    padding: "0.1rem 0.5rem",
    borderRadius: 4,
    fontSize: "0.7rem",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    fontWeight: 600,
  } as React.CSSProperties,
  requires: { color: "#64748b", fontSize: "0.78rem" } as React.CSSProperties,
};
