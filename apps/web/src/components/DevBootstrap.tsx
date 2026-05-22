// Widget dev: crea un tenant + utente admin e ottiene il JWT.
// Salva il token in localStorage cosi' diventa subito disponibile alle altre pagine.

import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
const TOKEN_KEY = "notai.jwt";

type BootstrapResponse = {
  tenant_id: string;
  user_id: string;
  token: string;
};

export function DevBootstrap({
  onToken,
}: {
  onToken?: (token: string, tenantId: string) => void;
}) {
  const [slug, setSlug] = useState(() => `studio-${Date.now().toString(36)}`);
  const [name, setName] = useState("Studio di prova");
  const [kind, setKind] = useState<"notarile" | "legale" | "misto">("misto");
  const [adminEmail, setAdminEmail] = useState("admin@studio.test");
  const [adminName, setAdminName] = useState("Admin");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BootstrapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE}/v1/dev/bootstrap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slug,
          name,
          kind,
          admin_email: adminEmail,
          admin_display_name: adminName,
        }),
      });
      if (!r.ok) {
        const txt = await r.text();
        throw new Error(`HTTP ${r.status}: ${txt}`);
      }
      const data = (await r.json()) as BootstrapResponse;
      setResult(data);
      localStorage.setItem(TOKEN_KEY, data.token);
      onToken?.(data.token, data.tenant_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!result) return;
    await navigator.clipboard.writeText(result.token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section style={styles.card}>
      <div style={styles.header}>
        <h3 style={styles.title}>Bootstrap tenant dev</h3>
        <span style={styles.badge}>solo dev</span>
      </div>
      <p style={styles.help}>
        Crea uno studio di prova + utente admin e genera un JWT valido per le altre
        pagine. Il token viene salvato in localStorage e ricaricato automaticamente.
      </p>

      <div style={styles.grid}>
        <Field label="Slug">
          <input value={slug} onChange={(e) => setSlug(e.target.value)} style={styles.input} />
        </Field>
        <Field label="Nome studio">
          <input value={name} onChange={(e) => setName(e.target.value)} style={styles.input} />
        </Field>
        <Field label="Tipo">
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as typeof kind)}
            style={styles.input}
          >
            <option value="misto">misto</option>
            <option value="notarile">notarile</option>
            <option value="legale">legale</option>
          </select>
        </Field>
        <Field label="Email admin">
          <input
            type="email"
            value={adminEmail}
            onChange={(e) => setAdminEmail(e.target.value)}
            style={styles.input}
          />
        </Field>
        <Field label="Nome admin">
          <input
            value={adminName}
            onChange={(e) => setAdminName(e.target.value)}
            style={styles.input}
          />
        </Field>
      </div>

      <button onClick={submit} disabled={busy} style={styles.button}>
        {busy ? "Sto creando..." : "Crea tenant + genera JWT"}
      </button>

      {error && <div style={styles.error}>{error}</div>}

      {result && (
        <div style={styles.result}>
          <div style={styles.resultLine}>
            <strong>tenant_id:</strong> <code>{result.tenant_id}</code>
          </div>
          <div style={styles.resultLine}>
            <strong>user_id:</strong> <code>{result.user_id}</code>
          </div>
          <div style={{ ...styles.resultLine, alignItems: "flex-start" }}>
            <strong>JWT:</strong>{" "}
            <code style={styles.tokenBlock} title={result.token}>
              {result.token.slice(0, 60)}…{result.token.slice(-12)}
            </code>
            <button onClick={copy} style={styles.copyBtn}>
              {copied ? "copiato ✓" : "copia"}
            </button>
          </div>
          <p style={styles.success}>
            Token salvato. Vai alla pagina <strong>Moduli</strong> per gestire i moduli del nuovo studio.
          </p>
        </div>
      )}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={styles.field}>
      <span style={styles.fieldLabel}>{label}</span>
      {children}
    </label>
  );
}

const styles = {
  card: {
    border: "1px solid #e2e8f0",
    background: "#fefce8",
    borderLeft: "4px solid #eab308",
    borderRadius: 6,
    padding: "1rem 1.25rem",
    marginTop: "2rem",
  } as React.CSSProperties,
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    marginBottom: "0.5rem",
  } as React.CSSProperties,
  title: { margin: 0, fontSize: "1.05rem", color: "#854d0e" },
  badge: {
    background: "#fef08a",
    color: "#854d0e",
    padding: "0.1rem 0.5rem",
    borderRadius: 4,
    fontSize: "0.7rem",
    textTransform: "uppercase",
    fontWeight: 600,
  } as React.CSSProperties,
  help: { color: "#78350f", fontSize: "0.9rem", margin: "0.25rem 0 1rem" },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: "0.75rem",
    marginBottom: "1rem",
  } as React.CSSProperties,
  field: { display: "flex", flexDirection: "column", gap: "0.25rem" } as React.CSSProperties,
  fieldLabel: { fontSize: "0.78rem", color: "#854d0e", fontWeight: 600 },
  input: {
    padding: "0.4rem 0.6rem",
    border: "1px solid #cbd5e1",
    borderRadius: 4,
    fontSize: "0.9rem",
    background: "white",
  } as React.CSSProperties,
  button: {
    padding: "0.6rem 1.25rem",
    background: "#854d0e",
    color: "white",
    border: "none",
    borderRadius: 4,
    cursor: "pointer",
    fontWeight: 600,
  } as React.CSSProperties,
  error: {
    marginTop: "0.75rem",
    background: "#fee2e2",
    color: "#7f1d1d",
    padding: "0.6rem",
    borderRadius: 4,
    fontSize: "0.85rem",
  } as React.CSSProperties,
  result: {
    marginTop: "1rem",
    background: "white",
    border: "1px solid #d1d5db",
    borderRadius: 4,
    padding: "0.75rem 1rem",
  } as React.CSSProperties,
  resultLine: {
    display: "flex",
    gap: "0.5rem",
    alignItems: "center",
    marginBottom: "0.4rem",
    fontSize: "0.85rem",
    flexWrap: "wrap",
  } as React.CSSProperties,
  tokenBlock: {
    fontFamily: "ui-monospace, Menlo, Consolas, monospace",
    fontSize: "0.78rem",
    background: "#f1f5f9",
    padding: "0.2rem 0.4rem",
    borderRadius: 3,
    wordBreak: "break-all",
  } as React.CSSProperties,
  copyBtn: {
    padding: "0.25rem 0.6rem",
    fontSize: "0.78rem",
    background: "#1e293b",
    color: "white",
    border: "none",
    borderRadius: 3,
    cursor: "pointer",
  } as React.CSSProperties,
  success: {
    marginTop: "0.5rem",
    color: "#166534",
    fontSize: "0.85rem",
  } as React.CSSProperties,
};
