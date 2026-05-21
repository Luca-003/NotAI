import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

type DiscoveredModel = {
  name: string;
  backend: "litellm" | "ollama";
  size_bytes: number | null;
  family: string | null;
  parameter_size: string | null;
  quantization: string | null;
};

type ModelsResponse = { count: number; models: DiscoveredModel[] };

type RoutingResponse = {
  routing: Record<string, string>;
  defaults_from_env: Record<string, string>;
  runtime_overrides: Record<string, string>;
};

const ROLES: { key: string; label: string; description: string }[] = [
  { key: "generation", label: "Generazione testo", description: "Redrafting clausole, riassunti" },
  { key: "extraction", label: "Estrazione strutturata", description: "Parsing visure, dati da documenti" },
  { key: "embeddings", label: "Embeddings (RAG)", description: "Vettorizzazione per ricerca semantica" },
  { key: "verifier", label: "Verifier (abstention)", description: "Cross-check per zero-allucinazione" },
  { key: "classification", label: "Classificazione/tagging", description: "Zero/few-shot su clausole" },
];

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

async function putJSON<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

async function deleteJSON<T>(url: string): Promise<T> {
  const r = await fetch(url, { method: "DELETE" });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function humanSize(bytes: number | null): string {
  if (bytes == null) return "-";
  const gb = bytes / (1024 ** 3);
  if (gb >= 1) return `${gb.toFixed(2)} GB`;
  const mb = bytes / (1024 ** 2);
  return `${mb.toFixed(0)} MB`;
}

export function LLMModelPicker() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});

  const models = useQuery({
    queryKey: ["llm", "models"],
    queryFn: () => getJSON<ModelsResponse>(`${API_BASE}/v1/llm/models`),
    refetchInterval: 30_000,
  });

  const routing = useQuery({
    queryKey: ["llm", "routing"],
    queryFn: () => getJSON<RoutingResponse>(`${API_BASE}/v1/llm/routing`),
  });

  const update = useMutation({
    mutationFn: (body: Record<string, string>) =>
      putJSON<RoutingResponse>(`${API_BASE}/v1/llm/routing`, body),
    onSuccess: () => {
      setDraft({});
      qc.invalidateQueries({ queryKey: ["llm", "routing"] });
    },
  });

  const clearOverrides = useMutation({
    mutationFn: () => deleteJSON<RoutingResponse>(`${API_BASE}/v1/llm/routing/overrides`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm", "routing"] }),
  });

  const allOptions = new Set<string>();
  for (const m of models.data?.models ?? []) allOptions.add(m.name);
  for (const v of Object.values(routing.data?.routing ?? {})) allOptions.add(v);
  const optionsList = Array.from(allOptions).sort();

  return (
    <section style={card}>
      <h2>Modelli LLM</h2>
      <p style={{ color: "#666", fontSize: "0.9rem" }}>
        L'app usa i modelli per <strong>ruolo</strong>. Cambia il modello associato a un ruolo
        per swappare il backend senza toccare il codice. Override in-memory in Fase 0;
        DB-persisted per-tenant in Fase 1.
      </p>

      <h3>Mappa attuale (ruolo &rarr; modello)</h3>
      <table style={table}>
        <thead>
          <tr>
            <th style={th}>Ruolo</th>
            <th style={th}>Modello attuale</th>
            <th style={th}>Nuovo (override)</th>
          </tr>
        </thead>
        <tbody>
          {ROLES.map((r) => {
            const current = routing.data?.routing?.[r.key] ?? "-";
            const isOverridden = (routing.data?.runtime_overrides ?? {})[r.key] !== undefined;
            return (
              <tr key={r.key}>
                <td style={td}>
                  <strong>{r.label}</strong>
                  <div style={{ fontSize: "0.8rem", color: "#777" }}>{r.description}</div>
                </td>
                <td style={td}>
                  <code>{current}</code>
                  {isOverridden && (
                    <span style={badge} title="override runtime attivo">
                      override
                    </span>
                  )}
                </td>
                <td style={td}>
                  <input
                    list={`models-${r.key}`}
                    placeholder={current}
                    value={draft[r.key] ?? ""}
                    onChange={(e) => setDraft({ ...draft, [r.key]: e.target.value })}
                    style={{ width: "100%", padding: "0.25rem" }}
                  />
                  <datalist id={`models-${r.key}`}>
                    {optionsList.map((opt) => (
                      <option key={opt} value={opt} />
                    ))}
                  </datalist>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
        <button
          style={btnPrimary}
          disabled={Object.keys(draft).length === 0 || update.isPending}
          onClick={() => update.mutate(draft)}
        >
          {update.isPending ? "Salvo..." : "Applica override"}
        </button>
        <button
          style={btnSecondary}
          disabled={Object.keys(routing.data?.runtime_overrides ?? {}).length === 0}
          onClick={() => clearOverrides.mutate()}
        >
          Torna ai default da env
        </button>
      </div>

      <h3 style={{ marginTop: "2rem" }}>Modelli scoperti</h3>
      {models.isLoading && <div>...</div>}
      {models.isError && <div style={{ color: "crimson" }}>errore: {String(models.error)}</div>}
      {models.data && (
        <table style={table}>
          <thead>
            <tr>
              <th style={th}>Nome</th>
              <th style={th}>Backend</th>
              <th style={th}>Famiglia</th>
              <th style={th}>Dimensione</th>
              <th style={th}>Quantizzazione</th>
            </tr>
          </thead>
          <tbody>
            {models.data.models.map((m) => (
              <tr key={`${m.backend}:${m.name}`}>
                <td style={td}>
                  <code>{m.name}</code>
                </td>
                <td style={td}>{m.backend}</td>
                <td style={td}>{m.family ?? "-"} {m.parameter_size ? `(${m.parameter_size})` : ""}</td>
                <td style={td}>{humanSize(m.size_bytes)}</td>
                <td style={td}>{m.quantization ?? "-"}</td>
              </tr>
            ))}
            {models.data.count === 0 && (
              <tr>
                <td colSpan={5} style={{ ...td, fontStyle: "italic", color: "#888" }}>
                  Nessun modello scoperto. Avvia LiteLLM o installa modelli con `ollama pull`.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </section>
  );
}

const card: React.CSSProperties = {
  marginTop: "2rem",
  padding: "1rem 1.5rem",
  border: "1px solid #ddd",
  borderRadius: 8,
  background: "#fafafa",
};
const table: React.CSSProperties = {
  borderCollapse: "collapse",
  width: "100%",
  marginTop: "0.5rem",
};
const th: React.CSSProperties = {
  textAlign: "left",
  padding: "0.5rem",
  borderBottom: "2px solid #999",
  fontSize: "0.85rem",
};
const td: React.CSSProperties = {
  padding: "0.5rem",
  borderBottom: "1px solid #eee",
  fontSize: "0.9rem",
  verticalAlign: "top",
};
const btnPrimary: React.CSSProperties = {
  padding: "0.5rem 1rem",
  background: "#2b6cb0",
  color: "white",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
};
const btnSecondary: React.CSSProperties = {
  padding: "0.5rem 1rem",
  background: "white",
  border: "1px solid #aaa",
  borderRadius: 4,
  cursor: "pointer",
};
const badge: React.CSSProperties = {
  marginLeft: "0.5rem",
  padding: "0.1rem 0.4rem",
  background: "#fed7aa",
  color: "#7c2d12",
  borderRadius: 4,
  fontSize: "0.7rem",
  textTransform: "uppercase",
};
