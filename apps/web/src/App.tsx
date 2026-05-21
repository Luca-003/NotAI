import { useQuery } from "@tanstack/react-query";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

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

export function App() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 10_000 });
  const ready = useQuery({ queryKey: ["readyz"], queryFn: fetchReadyz, refetchInterval: 10_000 });

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 720, margin: "0 auto" }}>
      <h1>NotAI</h1>
      <p style={{ color: "#555" }}>
        Piattaforma di automazione per studi notarili e legali italiani — skeleton Fase 0.
      </p>

      <section style={{ marginTop: "2rem" }}>
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

      <footer style={{ marginTop: "3rem", color: "#888", fontSize: "0.85rem" }}>
        Build dev — solo skeleton.
      </footer>
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
