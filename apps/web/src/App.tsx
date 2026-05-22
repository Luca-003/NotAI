import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DevBootstrap } from "./components/DevBootstrap";
import { LLMModelPicker } from "./components/LLMModelPicker";
import { GuidePage } from "./guide/GuidePage";
import { ModulesPage } from "./modules/ModulesPage";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

type Tab = "dashboard" | "guide" | "modules";

export function App() {
  const [tab, setTab] = useState<Tab>("dashboard");

  return (
    <div style={layout.app}>
      <header style={layout.topbar}>
        <div style={layout.brand}>
          <strong>NotAI</strong>
          <span style={layout.brandSub}>automazione studi notarili e legali</span>
        </div>
        <nav style={layout.nav}>
          <NavButton active={tab === "dashboard"} onClick={() => setTab("dashboard")}>
            Dashboard
          </NavButton>
          <NavButton active={tab === "modules"} onClick={() => setTab("modules")}>
            Moduli
          </NavButton>
          <NavButton active={tab === "guide"} onClick={() => setTab("guide")}>
            Guida
          </NavButton>
        </nav>
      </header>

      <main style={layout.main}>
        {tab === "dashboard" && <Dashboard />}
        {tab === "modules" && <ModulesPage />}
        {tab === "guide" && <GuidePage />}
      </main>

      <footer style={layout.footer}>
        Build dev — vincolo zero-allucinazione attivo.
      </footer>
    </div>
  );
}

function NavButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        ...layout.navBtn,
        ...(active ? layout.navBtnActive : {}),
      }}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Dashboard (originale: stato sistema + model picker)
// ---------------------------------------------------------------------------

type Health = { status: string };
type Ready = { status: string; checks: Record<string, string> };

async function fetchHealth(): Promise<Health> {
  const res = await fetch(`${API_BASE.replace(/\/api$/, "")}/health`);
  if (!res.ok) throw new Error(`health http ${res.status}`);
  return res.json();
}

async function fetchReadyz(): Promise<Ready> {
  const res = await fetch(`${API_BASE.replace(/\/api$/, "")}/readyz`);
  if (!res.ok) throw new Error(`readyz http ${res.status}`);
  return res.json();
}

function Dashboard() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 10_000 });
  const ready = useQuery({ queryKey: ["readyz"], queryFn: fetchReadyz, refetchInterval: 10_000 });

  return (
    <div style={{ maxWidth: 960 }}>
      <h1>Dashboard</h1>
      <section style={{ marginTop: "1rem" }}>
        <h2>Stato sistema</h2>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <tbody>
            <tr>
              <td style={cellLabel}>API liveness</td>
              <td style={cellValue}>
                {health.isLoading ? "..." : health.isError ? "errore" : health.data?.status}
              </td>
            </tr>
            <tr>
              <td style={cellLabel}>API readiness</td>
              <td style={cellValue}>
                {ready.isLoading ? "..." : ready.isError ? "errore" : ready.data?.status}
              </td>
            </tr>
          </tbody>
        </table>

        {ready.data && (
          <div style={{ marginTop: "1rem" }}>
            <h3>Dipendenze</h3>
            <ul>
              {Object.entries(ready.data.checks).map(([name, value]) => (
                <li key={name}>
                  <strong>{name}</strong>: {value}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <DevBootstrap />

      <LLMModelPicker />
    </div>
  );
}

const cellLabel: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid #eee",
  fontWeight: 600,
  width: "40%",
};

const cellValue: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid #eee",
};

const layout = {
  app: {
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
    minHeight: "100vh",
    background: "#f8fafc",
  } as React.CSSProperties,
  topbar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "1rem 2rem",
    borderBottom: "1px solid #e2e8f0",
    background: "white",
    position: "sticky",
    top: 0,
    zIndex: 10,
  } as React.CSSProperties,
  brand: { display: "flex", alignItems: "baseline", gap: "0.75rem" } as React.CSSProperties,
  brandSub: { color: "#64748b", fontSize: "0.85rem" } as React.CSSProperties,
  nav: { display: "flex", gap: "0.5rem" } as React.CSSProperties,
  navBtn: {
    padding: "0.45rem 0.9rem",
    border: "1px solid transparent",
    background: "transparent",
    cursor: "pointer",
    borderRadius: 4,
    fontSize: "0.92rem",
    color: "#475569",
  } as React.CSSProperties,
  navBtnActive: {
    background: "#1e293b",
    color: "white",
    fontWeight: 600,
  } as React.CSSProperties,
  main: { padding: "2rem", maxWidth: 1400, margin: "0 auto" } as React.CSSProperties,
  footer: {
    textAlign: "center",
    padding: "1rem",
    color: "#94a3b8",
    fontSize: "0.85rem",
    borderTop: "1px solid #e2e8f0",
    background: "white",
  } as React.CSSProperties,
};
