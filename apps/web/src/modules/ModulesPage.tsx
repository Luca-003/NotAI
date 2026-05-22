// Pagina admin per attivare/disattivare i moduli del tenant corrente.
// Usa la session dalla topbar: niente form, niente token manuale.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, type Session } from "../auth";

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

export function ModulesPage({
  session,
  onNeedLogin,
}: {
  session: Session | null;
  onNeedLogin: () => void;
}) {
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const qc = useQueryClient();

  const modules = useQuery({
    queryKey: ["modules", session?.token],
    queryFn: () => apiFetch<ModulesResponse>("/v1/modules", {}, session?.token),
    enabled: !!session,
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      apiFetch(
        `/v1/modules/${id}`,
        { method: "PUT", body: JSON.stringify({ enabled }) },
        session?.token,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modules", session?.token] }),
  });

  if (!session) {
    return (
      <div style={styles.empty}>
        <h2>Accedi per gestire i moduli</h2>
        <p style={{ color: "#64748b" }}>
          Premi <strong>Accedi (dev)</strong> in alto a destra per creare un tenant
          demo e visualizzare i moduli del tuo studio.
        </p>
        <button onClick={onNeedLogin} style={styles.bigLogin}>
          Accedi (dev) ora
        </button>
      </div>
    );
  }

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

      {modules.isError && <div style={styles.error}>Errore: {String(modules.error)}</div>}

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
                      richiede:{" "}
                      {m.requires
                        .map((r) => <code key={r}>{r}</code>)
                        .reduce<React.ReactNode[]>(
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
  empty: {
    textAlign: "center",
    padding: "3rem 1rem",
    color: "#475569",
  } as React.CSSProperties,
  bigLogin: {
    marginTop: "1rem",
    padding: "0.8rem 2rem",
    background: "#16a34a",
    color: "white",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontWeight: 700,
    fontSize: "1rem",
  } as React.CSSProperties,
  error: {
    background: "#fee2e2",
    border: "1px solid #f87171",
    color: "#7f1d1d",
    padding: "0.6rem",
    borderRadius: 4,
    marginBottom: "1rem",
  } as React.CSSProperties,
  filterBar: {
    display: "flex",
    gap: "0.5rem",
    marginBottom: "1rem",
    flexWrap: "wrap",
  } as React.CSSProperties,
  filterBtn: {
    padding: "0.35rem 0.75rem",
    border: "1px solid #cbd5e1",
    background: "white",
    borderRadius: 999,
    fontSize: "0.85rem",
    cursor: "pointer",
  } as React.CSSProperties,
  filterBtnActive: {
    background: "#1e293b",
    color: "white",
    borderColor: "#1e293b",
  } as React.CSSProperties,
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
  metaRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: "0.4rem",
    alignItems: "center",
    fontSize: "0.78rem",
  } as React.CSSProperties,
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
