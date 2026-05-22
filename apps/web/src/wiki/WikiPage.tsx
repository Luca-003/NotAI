// Tab Wiki: lista esempi di atto reali + upload + search semantica.
// Serve agli avvocati/notai per consultare casi simili e per "addestrare"
// il sistema con esempi catalogati.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { apiFetch, type Session } from "../auth";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

type ActExample = {
  id: string;
  tenant_id: string | null;
  template_id: string | null;
  title: string;
  description: string | null;
  tags: string[];
  source: string;
  license: string;
  is_anonymized: boolean;
  size_bytes: number;
  embedding_indexed: boolean;
  chunks_count: number;
  created_at: string;
};

type ExampleDetail = ActExample & {
  full_text: string;
  sections: unknown | null;
};

type SearchHit = {
  kind: "semantic" | "text";
  example_id: string;
  title: string;
  template_id: string | null;
  tags: string[];
  score: number | null;
  snippet: string;
};

type TemplateOption = { id: string; name: string; category: string };

export function WikiPage({
  session,
  onNeedLogin,
}: {
  session: Session | null;
  onNeedLogin: () => void;
}) {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterTemplate, setFilterTemplate] = useState<string>("");
  const [searchQ, setSearchQ] = useState("");
  const [showUpload, setShowUpload] = useState(false);

  if (!session) {
    return (
      <div style={{ textAlign: "center", padding: "3rem 1rem", color: "#475569" }}>
        <h2>Accedi per consultare la wiki di atti</h2>
        <button
          onClick={onNeedLogin}
          style={{
            marginTop: "1rem",
            padding: "0.8rem 2rem",
            background: "#16a34a",
            color: "white",
            border: "none",
            borderRadius: 6,
            cursor: "pointer",
            fontWeight: 700,
          }}
        >
          Accedi (dev) ora
        </button>
      </div>
    );
  }

  const examples = useQuery({
    queryKey: ["wiki-list", filterTemplate],
    queryFn: () =>
      apiFetch<ActExample[]>(
        `/v1/act-examples${filterTemplate ? `?template_id=${encodeURIComponent(filterTemplate)}` : ""}`,
        {},
        session.token,
      ),
  });

  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: () =>
      apiFetch<{ templates: TemplateOption[] }>("/v1/templates", {}, session.token),
    staleTime: 60_000,
  });

  const search = useQuery({
    queryKey: ["wiki-search", searchQ, filterTemplate],
    queryFn: () =>
      apiFetch<{ hits: SearchHit[]; count: number }>(
        `/v1/act-examples/search?q=${encodeURIComponent(searchQ)}${
          filterTemplate ? `&template_id=${encodeURIComponent(filterTemplate)}` : ""
        }`,
        {},
        session.token,
      ),
    enabled: searchQ.trim().length >= 2,
    staleTime: 5_000,
  });

  return (
    <div style={{ maxWidth: 1100, display: "grid", gridTemplateColumns: "320px 1fr", gap: "1.5rem" }}>
      <aside>
        <div style={{ marginBottom: "1rem" }}>
          <h1 style={{ margin: "0 0 0.25rem 0", fontSize: "1.4rem" }}>Wiki atti</h1>
          <p style={{ color: "#64748b", fontSize: "0.88rem", margin: 0 }}>
            Esempi reali di atti notarili e legali, ricercabili anche
            semanticamente. Usati dal sistema per suggerire clausole.
          </p>
        </div>

        <button
          onClick={() => setShowUpload((v) => !v)}
          style={{
            width: "100%",
            padding: "0.55rem 1rem",
            background: "#1e293b",
            color: "white",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
            fontWeight: 600,
            marginBottom: "1rem",
          }}
        >
          {showUpload ? "Annulla upload" : "+ Carica esempio"}
        </button>

        {showUpload && (
          <UploadForm
            session={session}
            templates={templates.data?.templates ?? []}
            onDone={() => {
              setShowUpload(false);
              qc.invalidateQueries({ queryKey: ["wiki-list"] });
            }}
          />
        )}

        <div style={{ marginBottom: "0.8rem" }}>
          <label style={{ fontSize: "0.78rem", color: "#475569", fontWeight: 600 }}>
            Filtra per template
          </label>
          <select
            value={filterTemplate}
            onChange={(e) => setFilterTemplate(e.target.value)}
            style={{
              width: "100%",
              padding: "0.4rem",
              border: "1px solid #cbd5e1",
              borderRadius: 4,
              fontSize: "0.85rem",
              marginTop: "0.2rem",
            }}
          >
            <option value="">Tutti</option>
            {templates.data?.templates.map((t) => (
              <option key={t.id} value={t.id}>
                [{t.category}] {t.name}
              </option>
            ))}
          </select>
        </div>

        <input
          type="search"
          placeholder="Ricerca semantica (es. 'rinuncia ipoteca')"
          value={searchQ}
          onChange={(e) => setSearchQ(e.target.value)}
          style={{
            width: "100%",
            padding: "0.45rem 0.6rem",
            border: "1px solid #cbd5e1",
            borderRadius: 4,
            fontSize: "0.88rem",
            marginBottom: "0.8rem",
          }}
        />

        {searchQ.trim().length >= 2 && search.data && (
          <div style={{ marginBottom: "1rem" }}>
            <h4 style={{ fontSize: "0.85rem", color: "#475569", margin: "0 0 0.4rem" }}>
              {search.data.count} risultati
            </h4>
            {search.data.hits.map((h) => (
              <button
                key={`${h.example_id}-${h.kind}`}
                onClick={() => setSelectedId(h.example_id)}
                style={hitBox}
              >
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong style={{ fontSize: "0.85rem" }}>{h.title}</strong>
                  {h.score != null && (
                    <span style={{ fontSize: "0.7rem", color: "#16a34a" }}>
                      {(h.score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <div style={{ fontSize: "0.72rem", color: "#94a3b8", margin: "0.15rem 0" }}>
                  {h.kind === "semantic" ? "🔍 semantica" : "📝 testo"}{" "}
                  {h.template_id && `· ${h.template_id}`}
                </div>
                <div style={{ fontSize: "0.78rem", color: "#475569", fontStyle: "italic" }}>
                  {h.snippet}…
                </div>
              </button>
            ))}
          </div>
        )}

        <h4 style={{ fontSize: "0.85rem", color: "#475569", margin: "0 0 0.4rem" }}>
          Esempi disponibili ({examples.data?.length ?? 0})
        </h4>
        {examples.isLoading && <div>Carico...</div>}
        {examples.data && examples.data.length === 0 && (
          <div style={{ color: "#94a3b8", fontSize: "0.88rem", fontStyle: "italic" }}>
            Nessun esempio. Caricane uno per cominciare.
          </div>
        )}
        {examples.data?.map((ex) => (
          <button
            key={ex.id}
            onClick={() => setSelectedId(ex.id)}
            style={{
              ...listItem,
              ...(selectedId === ex.id ? { background: "#dbeafe", borderColor: "#3b82f6" } : {}),
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <strong style={{ fontSize: "0.88rem" }}>{ex.title}</strong>
              {ex.tenant_id === null && (
                <span style={{ fontSize: "0.65rem", background: "#dcfce7", color: "#166534", padding: "0.05rem 0.4rem", borderRadius: 2 }}>
                  GLOBAL
                </span>
              )}
            </div>
            {ex.template_id && (
              <div style={{ fontSize: "0.72rem", color: "#64748b", marginTop: "0.15rem" }}>
                {ex.template_id}
              </div>
            )}
            {ex.tags.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.2rem", marginTop: "0.25rem" }}>
                {ex.tags.map((t) => (
                  <span key={t} style={tagBadge}>#{t}</span>
                ))}
              </div>
            )}
            <div style={{ fontSize: "0.7rem", color: "#94a3b8", marginTop: "0.25rem" }}>
              {humanSize(ex.size_bytes)} · {ex.embedding_indexed ? "✓ indicizzato" : "no embed"}
              {ex.is_anonymized && " · anonimizzato"}
            </div>
          </button>
        ))}
      </aside>

      <main>
        {selectedId ? (
          <ExampleDetailView session={session} exampleId={selectedId} />
        ) : (
          <div style={{ padding: "2rem", textAlign: "center", color: "#94a3b8" }}>
            Seleziona un esempio dalla lista o cerca semantica per cominciare.
          </div>
        )}
      </main>
    </div>
  );
}

function UploadForm({
  session,
  templates,
  onDone,
}: {
  session: Session;
  templates: TemplateOption[];
  onDone: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [tags, setTags] = useState("");
  const [license, setLicense] = useState("internal_only");
  const [isAnon, setIsAnon] = useState(false);
  const [isGlobal, setIsGlobal] = useState(false);

  const upload = useMutation({
    mutationFn: async (e: React.FormEvent) => {
      e.preventDefault();
      const f = fileRef.current?.files?.[0];
      if (!f) throw new Error("seleziona un file");
      const fd = new FormData();
      fd.append("file", f);
      fd.append("title", title || f.name);
      if (templateId) fd.append("template_id", templateId);
      fd.append("tags", tags);
      fd.append("license", license);
      fd.append("is_anonymized", String(isAnon));
      fd.append("is_global", String(isGlobal));
      const r = await fetch(`${API_BASE}/v1/act-examples`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.token}` },
        body: fd,
      });
      if (!r.ok) {
        const txt = await r.text().catch(() => "");
        throw new Error(`HTTP ${r.status}: ${txt}`);
      }
      return r.json();
    },
    onSuccess: () => onDone(),
  });

  return (
    <form
      onSubmit={upload.mutate}
      style={{
        background: "#fff7ed",
        border: "1px solid #fed7aa",
        borderRadius: 6,
        padding: "0.8rem",
        marginBottom: "1rem",
        fontSize: "0.85rem",
      }}
    >
      <input type="file" ref={fileRef} accept=".txt,.md,text/*" required style={uplInput} />
      <input
        type="text"
        placeholder="Titolo (es. 'Compravendita Rossi-Bianchi 2024')"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        style={uplInput}
      />
      <select value={templateId} onChange={(e) => setTemplateId(e.target.value)} style={uplInput}>
        <option value="">Nessun template specifico</option>
        {templates.map((t) => (
          <option key={t.id} value={t.id}>
            [{t.category}] {t.id}
          </option>
        ))}
      </select>
      <input
        type="text"
        placeholder="Tag (es. milano, prima_casa, 2024)"
        value={tags}
        onChange={(e) => setTags(e.target.value)}
        style={uplInput}
      />
      <select value={license} onChange={(e) => setLicense(e.target.value)} style={uplInput}>
        <option value="internal_only">Solo studio (internal_only)</option>
        <option value="anonymized">Anonimizzato (anonymized)</option>
        <option value="consent_given">Consenso parti (consent_given)</option>
        <option value="public">Pubblico</option>
      </select>
      <label style={{ display: "block", margin: "0.4rem 0" }}>
        <input
          type="checkbox"
          checked={isAnon}
          onChange={(e) => setIsAnon(e.target.checked)}
          style={{ marginRight: "0.3rem" }}
        />
        Anonimizzato (rimossi nomi, CF)
      </label>
      <label style={{ display: "block", marginBottom: "0.6rem" }}>
        <input
          type="checkbox"
          checked={isGlobal}
          onChange={(e) => setIsGlobal(e.target.checked)}
          style={{ marginRight: "0.3rem" }}
        />
        Condividi (visibile a tutti) - richiede anonimizzato o licenza pubblica
      </label>
      <button
        type="submit"
        disabled={upload.isPending}
        style={{
          width: "100%",
          padding: "0.5rem",
          background: "#ea580c",
          color: "white",
          border: "none",
          borderRadius: 4,
          cursor: "pointer",
          fontWeight: 600,
        }}
      >
        {upload.isPending ? "Caricamento..." : "Carica"}
      </button>
      {upload.isError && (
        <div style={{ color: "#7f1d1d", marginTop: "0.4rem", fontSize: "0.8rem" }}>
          {String(upload.error)}
        </div>
      )}
    </form>
  );
}

function ExampleDetailView({
  session,
  exampleId,
}: {
  session: Session;
  exampleId: string;
}) {
  const ex = useQuery({
    queryKey: ["wiki-detail", exampleId],
    queryFn: () =>
      apiFetch<ExampleDetail>(`/v1/act-examples/${exampleId}`, {}, session.token),
  });

  if (ex.isLoading) return <div>Carico...</div>;
  if (ex.isError) return <div style={{ color: "#7f1d1d" }}>{String(ex.error)}</div>;
  if (!ex.data) return null;

  return (
    <article>
      <header style={{ marginBottom: "1rem" }}>
        <h2 style={{ margin: 0 }}>{ex.data.title}</h2>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
          {ex.data.template_id && (
            <code style={{ fontSize: "0.78rem", background: "#dbeafe", color: "#1e3a8a", padding: "0.1rem 0.5rem", borderRadius: 3 }}>
              {ex.data.template_id}
            </code>
          )}
          <span style={{ fontSize: "0.78rem", color: "#64748b" }}>
            {ex.data.license}{ex.data.is_anonymized && " · anonimizzato"} · {ex.data.chunks_count} chunks
          </span>
          {ex.data.tenant_id === null && (
            <span style={{ fontSize: "0.7rem", background: "#dcfce7", color: "#166534", padding: "0.1rem 0.5rem", borderRadius: 3, fontWeight: 600 }}>
              GLOBAL
            </span>
          )}
        </div>
        {ex.data.tags.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", marginTop: "0.5rem" }}>
            {ex.data.tags.map((t) => (
              <span key={t} style={tagBadge}>#{t}</span>
            ))}
          </div>
        )}
        {ex.data.description && (
          <p style={{ color: "#475569", marginTop: "0.75rem" }}>{ex.data.description}</p>
        )}
      </header>
      <div
        style={{
          background: "#fafaf9",
          border: "1px solid #e7e5e4",
          borderRadius: 6,
          padding: "1.25rem 1.5rem",
          maxHeight: 720,
          overflowY: "auto",
          fontFamily: "Georgia, serif",
          lineHeight: 1.7,
          whiteSpace: "pre-wrap",
          fontSize: "0.92rem",
        }}
      >
        {ex.data.full_text}
      </div>
    </article>
  );
}

function humanSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

const listItem: React.CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  padding: "0.55rem 0.7rem",
  background: "white",
  border: "1px solid #e2e8f0",
  borderRadius: 4,
  cursor: "pointer",
  marginBottom: "0.4rem",
};

const hitBox: React.CSSProperties = {
  ...listItem,
  background: "#f8fafc",
  borderColor: "#cbd5e1",
};

const tagBadge: React.CSSProperties = {
  fontSize: "0.68rem",
  background: "#f1f5f9",
  color: "#475569",
  padding: "0.05rem 0.4rem",
  borderRadius: 2,
};

const uplInput: React.CSSProperties = {
  width: "100%",
  padding: "0.35rem 0.5rem",
  border: "1px solid #cbd5e1",
  borderRadius: 3,
  fontSize: "0.85rem",
  marginBottom: "0.4rem",
};
