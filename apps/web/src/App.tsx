import { useQuery } from "@tanstack/react-query";
import { rootUrl, useSession } from "./auth";
import { LLMModelPicker } from "./components/LLMModelPicker";
import { DemoLoader } from "./demo/DemoLoader";
import { GuidePage } from "./guide/GuidePage";
import { ModulesPage } from "./modules/ModulesPage";
import { PracticesPage } from "./practices/PracticesPage";
import { WikiPage } from "./wiki/WikiPage";
import { buildHref, useRoute, type Tab } from "./routing";
import { WorkspaceTree } from "./workspace/WorkspaceTree";

export function App() {
  const { route, goto } = useRoute();
  const tab = route.tab;
  const { session, loading, error, login, logout } = useSession();

  return (
    <div style={layout.app}>
      <header style={layout.topbar}>
        <div style={layout.brand}>
          <strong>NotAI/O</strong>
          <span style={layout.brandSub}>automazione studi notarili e legali</span>
        </div>

        <nav style={layout.nav}>
          <NavLink href={buildHref("dashboard")} active={tab === "dashboard"}>Dashboard</NavLink>
          <NavLink href={buildHref("practices")} active={tab === "practices"}>Pratiche</NavLink>
          <NavLink href={buildHref("wiki")} active={tab === "wiki"}>Wiki</NavLink>
          <NavLink href={buildHref("modules")} active={tab === "modules"}>Moduli</NavLink>
          <NavLink href={buildHref("guide")} active={tab === "guide"}>Guida</NavLink>
        </nav>

        <div style={layout.session}>
          {session ? (
            <>
              <span style={layout.sessionInfo}>
                Studio Demo · <code style={layout.tenantId}>{session.tenantId.slice(0, 8)}…</code>
              </span>
              <button onClick={logout} style={layout.logoutBtn}>Esci</button>
            </>
          ) : (
            <button onClick={login} disabled={loading} style={layout.loginBtn}>
              {loading ? "Accesso..." : "Accedi (dev)"}
            </button>
          )}
        </div>
      </header>

      {error && <div style={layout.errorBar}>Errore login: {error}</div>}

      <div style={layout.body}>
        {session && <WorkspaceTree session={session} route={route} />}

        <main style={layout.main}>
          {tab === "dashboard" && <Dashboard session={session} goto={goto} />}
          {tab === "practices" && (
            <PracticesPage
              session={session}
              onNeedLogin={login}
              route={route}
              goto={goto}
            />
          )}
          {tab === "wiki" && <WikiPage session={session} onNeedLogin={login} />}
          {tab === "modules" && <ModulesPage session={session} onNeedLogin={login} />}
          {tab === "guide" && <GuidePage />}
        </main>
      </div>

      <footer style={layout.footer}>
        Build dev — vincolo zero-allucinazione attivo.
      </footer>
    </div>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      style={{
        ...layout.navBtn,
        ...(active ? layout.navBtnActive : {}),
        textDecoration: "none",
        display: "inline-block",
      }}
    >
      {children}
    </a>
  );
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

type Ready = { status: string; checks: Record<string, string> };

async function fetchReadyz(): Promise<Ready> {
  const res = await fetch(`${rootUrl()}/readyz`);
  if (!res.ok) throw new Error(`readyz http ${res.status}`);
  return res.json();
}

function Dashboard({
  session,
  goto,
}: {
  session: import("./auth").Session | null;
  goto: (tab: Tab, opts?: { practiceId?: string; actId?: string }) => void;
}) {
  // Una sola query: /readyz e' superset di /health (se ready=ok l'API e' viva
  // per definizione). Risparmia un endpoint di polling ogni 10s.
  const ready = useQuery({ queryKey: ["readyz"], queryFn: fetchReadyz, refetchInterval: 10_000 });
  const liveness = ready.isLoading ? "..." : ready.isError ? "errore" : "ok";

  return (
    <div style={{ maxWidth: 960 }}>
      <h1>Dashboard</h1>
      <section style={{ marginTop: "1rem" }}>
        <h2>Stato sistema</h2>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <tbody>
            <tr>
              <td style={cellLabel}>API liveness</td>
              <td style={cellValue}>{liveness}</td>
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

      <DemoLoader session={session} goto={goto} />

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
    gap: "1rem",
  } as React.CSSProperties,
  brand: { display: "flex", alignItems: "baseline", gap: "0.75rem" } as React.CSSProperties,
  brandSub: { color: "#64748b", fontSize: "0.85rem" } as React.CSSProperties,
  nav: { display: "flex", gap: "0.5rem", flex: 1, justifyContent: "center" } as React.CSSProperties,
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
  session: { display: "flex", alignItems: "center", gap: "0.75rem" } as React.CSSProperties,
  sessionInfo: { color: "#475569", fontSize: "0.88rem" } as React.CSSProperties,
  tenantId: {
    fontFamily: "ui-monospace, Menlo, Consolas, monospace",
    fontSize: "0.8rem",
    background: "#f1f5f9",
    padding: "0.1rem 0.35rem",
    borderRadius: 3,
  } as React.CSSProperties,
  loginBtn: {
    padding: "0.55rem 1.25rem",
    background: "#16a34a",
    color: "white",
    border: "none",
    borderRadius: 4,
    cursor: "pointer",
    fontWeight: 700,
    fontSize: "0.95rem",
    boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
  } as React.CSSProperties,
  logoutBtn: {
    padding: "0.4rem 0.9rem",
    background: "white",
    color: "#475569",
    border: "1px solid #cbd5e1",
    borderRadius: 4,
    cursor: "pointer",
    fontSize: "0.85rem",
  } as React.CSSProperties,
  errorBar: {
    background: "#fee2e2",
    color: "#7f1d1d",
    padding: "0.6rem 2rem",
    borderBottom: "1px solid #f87171",
    fontSize: "0.88rem",
  } as React.CSSProperties,
  body: { display: "flex", flex: 1, minHeight: "calc(100vh - 70px)" } as React.CSSProperties,
  main: { padding: "1.5rem 2rem", flex: 1, overflowX: "auto" } as React.CSSProperties,
  footer: {
    textAlign: "center",
    padding: "1rem",
    color: "#94a3b8",
    fontSize: "0.85rem",
    borderTop: "1px solid #e2e8f0",
    background: "white",
  } as React.CSSProperties,
};
