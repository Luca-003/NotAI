// Workspace documenti per un atto: upload (drag-drop + picker), lista, preview.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { apiFetch, type Session } from "../auth";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

type Doc = {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  kind: string;
  sha256: string;
  created_at: string;
  ingestion_status: "pending" | "in_progress" | "done" | "failed" | "skipped";
  ingestion_error: string | null;
  ingested_at: string | null;
};

type ExtractedEntity = {
  type: string;
  value: string;
  confidence: number;
};

type ChunkClassification = {
  abstained?: boolean;
  abstain_reason?: string | null;
  document_type?: string;
  entities?: ExtractedEntity[];
  summary?: string | null;
  suggested_tags?: string[];
  source_refs?: { citation: string; score: number | null }[];
  confidence?: number;
  error?: string;
};

type Chunk = {
  id: string;
  document_id: string;
  ordering: number;
  text: string;
  char_start: number;
  char_end: number;
  page_number: number | null;
  embedding_indexed: boolean;
  token_count: number | null;
  classification: ChunkClassification | null;
  classification_status: "pending" | "in_progress" | "done" | "abstained" | "failed" | "skipped";
  classified_at: string | null;
};

type DocumentClassificationSummary = {
  document_id: string;
  chunks_count: number;
  status_counts: Record<string, number>;
  document_type: string | null;
  document_type_distribution: Record<string, number>;
  entities: ExtractedEntity[];
  tags: string[];
  summaries: string[];
};

export function DocumentsWorkspace({
  session,
  actId,
  selectedSource,
  onClearSelection,
}: {
  session: Session;
  actId: string;
  selectedSource?: { documentId: string; chunkId: string } | null;
  onClearSelection?: () => void;
}) {
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [highlightChunkId, setHighlightChunkId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Quando arriva una selectedSource dal DraftViewer, apri il documento sorgente
  // e segna il chunk da evidenziare.
  useEffect(() => {
    if (selectedSource) {
      setSelectedId(selectedSource.documentId);
      setHighlightChunkId(selectedSource.chunkId);
    }
  }, [selectedSource]);

  const docs = useQuery({
    queryKey: ["docs", actId],
    queryFn: () => apiFetch<Doc[]>(`/v1/acts/${actId}/documents`, {}, session.token),
    // Polling finche' qualche documento e' in pending/in_progress
    refetchInterval: (q) => {
      const data = q.state.data as Doc[] | undefined;
      if (!data) return 3_000;
      const pending = data.some(
        (d) => d.ingestion_status === "pending" || d.ingestion_status === "in_progress",
      );
      return pending ? 3_000 : false;
    },
  });

  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      const results: Doc[] = [];
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", f);
        fd.append("kind", "input_source");
        fd.append("act_id", actId);
        const r = await fetch(`${API_BASE}/v1/documents`, {
          method: "POST",
          headers: { Authorization: `Bearer ${session.token}` },
          body: fd,
        });
        if (!r.ok) {
          const txt = await r.text().catch(() => "");
          throw new Error(`${f.name}: HTTP ${r.status} ${txt}`);
        }
        results.push((await r.json()) as Doc);
      }
      return results;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs", actId] }),
  });

  const remove = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/v1/documents/${id}`, { method: "DELETE" }, session.token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs", actId] }),
  });

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) upload.mutate(e.dataTransfer.files);
  };

  const inputDocs = (docs.data ?? []).filter((d) => d.kind === "input_source" || d.kind === "allegato");
  const outputDocs = (docs.data ?? []).filter((d) => !["input_source", "allegato"].includes(d.kind));

  return (
    <section style={styles.card}>
      <h3 style={styles.title}>Documenti del fascicolo</h3>
      <p style={styles.help}>
        Carica visure, contratti preliminari, identita', perizie: NotAI li
        catalogo&#769; e li user&#224; per generare la bozza dell'atto, mantenendo
        la tracciabilita&#769; (output &harr; sorgente di input).
      </p>

      <ActSearchBar actId={actId} session={session} onJumpToChunk={(docId, chunkId) => { setSelectedId(docId); setHighlightChunkId(chunkId); }} query={searchQuery} setQuery={setSearchQuery} />

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        style={{
          ...styles.dropzone,
          background: dragOver ? "#eff6ff" : "#f8fafc",
          borderColor: dragOver ? "#3b82f6" : "#cbd5e1",
        }}
      >
        <div style={{ fontSize: "0.95rem", color: "#475569", marginBottom: "0.5rem" }}>
          Trascina i file qui (PDF, DOCX, JPG, PNG, MD) — max 50 MB ciascuno
        </div>
        <button onClick={() => fileInput.current?.click()} style={styles.pickerBtn}>
          Oppure scegli dai file
        </button>
        <input
          ref={fileInput}
          type="file"
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) upload.mutate(e.target.files);
            e.target.value = "";
          }}
        />
        {upload.isPending && <div style={styles.uploading}>Carico...</div>}
        {upload.isError && <div style={styles.error}>{String(upload.error)}</div>}
      </div>

      <DocumentList
        title="Input forniti dal notaio"
        docs={inputDocs}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onDelete={(id) => remove.mutate(id)}
        emptyMsg="Nessun documento ancora caricato. Trascina o scegli un file qui sopra."
        session={session}
      />

      <DocumentList
        title="Output prodotti dal sistema"
        docs={outputDocs}
        selectedId={selectedId}
        onSelect={setSelectedId}
        emptyMsg="L'atto bozza apparir&agrave; qui dopo aver avviato il workflow."
        session={session}
      />

      {selectedId && (
        <DocumentPreview
          documentId={selectedId}
          session={session}
          highlightChunkId={highlightChunkId}
          onClose={() => {
            setSelectedId(null);
            setHighlightChunkId(null);
            onClearSelection?.();
          }}
        />
      )}
    </section>
  );
}

function DocumentList({
  title,
  docs,
  selectedId,
  onSelect,
  onDelete,
  emptyMsg,
  session,
}: {
  title: string;
  docs: Doc[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete?: (id: string) => void;
  emptyMsg: string;
  session: Session;
}) {
  return (
    <div style={{ marginTop: "1.25rem" }}>
      <h4 style={styles.subtitle}>
        {title} <span style={styles.count}>({docs.length})</span>
      </h4>
      {docs.length === 0 ? (
        <div style={styles.emptyList}>{emptyMsg}</div>
      ) : (
        <ul style={styles.list}>
          {docs.map((d) => (
            <li
              key={d.id}
              style={{
                ...styles.docRow,
                ...(selectedId === d.id ? styles.docRowActive : {}),
              }}
            >
              <div style={{ flex: 1 }}>
                <button onClick={() => onSelect(d.id)} style={styles.docMain}>
                  <span style={styles.mimeIcon}>{mimeIcon(d.mime_type)}</span>
                  <span style={styles.docInfo}>
                    <strong style={{ fontSize: "0.92rem" }}>{d.filename}</strong>
                    <span style={styles.docMeta}>
                      {d.mime_type} · {humanSize(d.size_bytes)} ·{" "}
                      <code style={{ fontSize: "0.7rem" }}>{d.sha256.slice(0, 10)}…</code>
                    </span>
                  </span>
                  <IngestionBadge doc={d} />
                </button>
                <DocumentClassificationStrip
                  documentId={d.id}
                  session={session}
                  ingestionStatus={d.ingestion_status}
                />
              </div>
              {onDelete && (
                <button
                  onClick={() => onDelete(d.id)}
                  style={styles.deleteBtn}
                  title="Rimuovi (soft delete)"
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ActSearchBar({
  actId,
  session,
  onJumpToChunk,
  query,
  setQuery,
}: {
  actId: string;
  session: Session;
  onJumpToChunk: (documentId: string, chunkId: string) => void;
  query: string;
  setQuery: (q: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const trimmed = query.trim();
  const results = useQuery({
    queryKey: ["act-search", actId, trimmed],
    queryFn: () =>
      apiFetch<{
        input_hits: {
          chunk_id: string;
          document_id: string;
          filename: string;
          ordering: number;
          page_number: number | null;
          document_type: string | null;
          snippet: string;
        }[];
        output_hits: {
          document_id: string;
          filename: string;
          section_id: string;
          section_title: string;
          snippet: string;
        }[];
        total: number;
      }>(`/v1/acts/${actId}/search?q=${encodeURIComponent(trimmed)}`, {}, session.token),
    enabled: trimmed.length >= 2,
    staleTime: 5_000,
  });

  return (
    <div style={{ marginBottom: "1rem", position: "relative" }}>
      <input
        type="search"
        placeholder="Cerca nel fascicolo (nome, indirizzo, foglio catastale, norma...)"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        style={{
          width: "100%",
          padding: "0.55rem 0.8rem",
          fontSize: "0.92rem",
          border: "1px solid #cbd5e1",
          borderRadius: 4,
        }}
      />
      {open && trimmed.length >= 2 && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            background: "white",
            border: "1px solid #cbd5e1",
            borderTop: "none",
            borderRadius: "0 0 4px 4px",
            maxHeight: 380,
            overflowY: "auto",
            zIndex: 5,
            boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
          }}
        >
          {results.isLoading && <div style={{ padding: "0.6rem" }}>Cerco...</div>}
          {results.isError && (
            <div style={{ padding: "0.6rem", color: "#7f1d1d" }}>
              Errore: {String(results.error)}
            </div>
          )}
          {results.data && (
            <>
              {results.data.total === 0 && (
                <div style={{ padding: "0.8rem", color: "#94a3b8", fontSize: "0.88rem" }}>
                  Nessun risultato per "{trimmed}"
                </div>
              )}
              {results.data.input_hits.length > 0 && (
                <div>
                  <div style={searchCategory}>📥 Input ({results.data.input_hits.length})</div>
                  {results.data.input_hits.map((h) => (
                    <button
                      key={h.chunk_id}
                      onClick={() => {
                        onJumpToChunk(h.document_id, h.chunk_id);
                        setOpen(false);
                      }}
                      style={searchHit}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                        <strong style={{ fontSize: "0.85rem" }}>{h.filename}</strong>
                        {h.document_type && (
                          <code style={{ fontSize: "0.7rem", background: "#dbeafe", color: "#1e3a8a", padding: "0.05rem 0.4rem", borderRadius: 2 }}>
                            {h.document_type.replace(/_/g, " ")}
                          </code>
                        )}
                      </div>
                      <div style={{ color: "#64748b", fontSize: "0.78rem", marginTop: "0.2rem" }}>
                        chunk #{h.ordering}{h.page_number != null && ` · pag. ${h.page_number}`}
                      </div>
                      <div style={searchSnippet}>{h.snippet}</div>
                    </button>
                  ))}
                </div>
              )}
              {results.data.output_hits.length > 0 && (
                <div>
                  <div style={searchCategory}>📤 Output ({results.data.output_hits.length})</div>
                  {results.data.output_hits.map((h) => (
                    <div key={`${h.document_id}-${h.section_id}`} style={{ ...searchHit, cursor: "default" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                        <strong style={{ fontSize: "0.85rem" }}>{h.section_title}</strong>
                        <span style={{ fontSize: "0.7rem", color: "#94a3b8" }}>{h.filename}</span>
                      </div>
                      <div style={searchSnippet}>{h.snippet}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
          <button
            onClick={() => setOpen(false)}
            style={{
              width: "100%",
              padding: "0.4rem",
              background: "#f1f5f9",
              border: "none",
              borderTop: "1px solid #e2e8f0",
              cursor: "pointer",
              fontSize: "0.78rem",
              color: "#475569",
            }}
          >
            Chiudi
          </button>
        </div>
      )}
    </div>
  );
}

const searchCategory: React.CSSProperties = {
  padding: "0.4rem 0.75rem",
  background: "#f8fafc",
  fontSize: "0.78rem",
  fontWeight: 600,
  color: "#475569",
  borderBottom: "1px solid #e2e8f0",
};

const searchHit: React.CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  padding: "0.6rem 0.75rem",
  background: "transparent",
  border: "none",
  borderBottom: "1px solid #f1f5f9",
  cursor: "pointer",
  fontSize: "0.85rem",
};

const searchSnippet: React.CSSProperties = {
  fontSize: "0.78rem",
  color: "#334155",
  marginTop: "0.3rem",
  fontStyle: "italic",
  lineHeight: 1.4,
};


function DocumentClassificationStrip({
  documentId,
  session,
  ingestionStatus,
}: {
  documentId: string;
  session: Session;
  ingestionStatus: Doc["ingestion_status"];
}) {
  const summary = useQuery({
    queryKey: ["doc-classification", documentId],
    queryFn: () =>
      apiFetch<DocumentClassificationSummary>(
        `/v1/documents/${documentId}/classification`,
        {},
        session.token,
      ),
    enabled: ingestionStatus === "done",
    refetchInterval: (q) => {
      const data = q.state.data as DocumentClassificationSummary | undefined;
      if (!data) return 4_000;
      const pending =
        (data.status_counts.pending ?? 0) + (data.status_counts.in_progress ?? 0);
      return pending > 0 ? 4_000 : false;
    },
  });

  if (!summary.data) return null;
  const d = summary.data;
  const dtype = d.document_type;
  if (!dtype && d.entities.length === 0 && d.tags.length === 0) return null;

  return (
    <div style={styles.classStrip}>
      {dtype && (
        <span style={{ ...styles.classBadge, background: "#dbeafe", color: "#1e3a8a" }}>
          {dtype.replace(/_/g, " ")}
        </span>
      )}
      {d.entities.slice(0, 3).map((e, i) => (
        <span key={i} style={styles.classBadge} title={e.type}>
          {e.value.length > 28 ? e.value.slice(0, 26) + "…" : e.value}
        </span>
      ))}
      {d.entities.length > 3 && (
        <span style={styles.classMore}>+{d.entities.length - 3} entita'</span>
      )}
    </div>
  );
}


function IngestionBadge({ doc }: { doc: Doc }) {
  const conf: Record<Doc["ingestion_status"], { label: string; bg: string; fg: string }> = {
    pending: { label: "in coda", bg: "#fef3c7", fg: "#78350f" },
    in_progress: { label: "elaboro…", bg: "#dbeafe", fg: "#1e40af" },
    done: { label: "letto", bg: "#dcfce7", fg: "#166534" },
    failed: { label: "errore", bg: "#fee2e2", fg: "#7f1d1d" },
    skipped: { label: "non leggibile", bg: "#f1f5f9", fg: "#64748b" },
  };
  const c = conf[doc.ingestion_status];
  return (
    <span
      title={doc.ingestion_error ?? doc.ingestion_status}
      style={{
        padding: "0.1rem 0.5rem",
        background: c.bg,
        color: c.fg,
        borderRadius: 999,
        fontSize: "0.7rem",
        textTransform: "uppercase",
        letterSpacing: "0.03em",
        fontWeight: 600,
        whiteSpace: "nowrap",
        marginLeft: "auto",
      }}
    >
      {c.label}
    </span>
  );
}


function DocumentPreview({
  documentId,
  session,
  highlightChunkId,
  onClose,
}: {
  documentId: string;
  session: Session;
  highlightChunkId?: string | null;
  onClose: () => void;
}) {
  const url = `${API_BASE}/v1/documents/${documentId}/content`;
  // Per i tipi visibili nel browser, usiamo un blob URL con il token in
  // Authorization. Il browser non puo' passare header a un iframe src diretto,
  // quindi fetchamo il blob e generiamo un objectURL.
  const blobQ = useQuery({
    queryKey: ["doc-blob", documentId],
    queryFn: async () => {
      const r = await fetch(url, { headers: { Authorization: `Bearer ${session.token}` } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      const objectUrl = URL.createObjectURL(blob);
      return { objectUrl, mime: blob.type };
    },
    staleTime: Infinity,
  });

  return (
    <div style={styles.preview}>
      <div style={styles.previewHeader}>
        <strong style={{ fontSize: "0.95rem" }}>Anteprima documento</strong>
        <button onClick={onClose} style={styles.previewClose}>chiudi</button>
      </div>
      {blobQ.isLoading && <div>Carico...</div>}
      {blobQ.isError && <div style={styles.error}>{String(blobQ.error)}</div>}
      {blobQ.data && (
        <div style={styles.previewBody}>
          {blobQ.data.mime.startsWith("image/") ? (
            <img src={blobQ.data.objectUrl} alt="" style={{ maxWidth: "100%", maxHeight: 600 }} />
          ) : blobQ.data.mime === "application/pdf" ? (
            <iframe
              src={blobQ.data.objectUrl}
              title="pdf"
              style={{ width: "100%", height: 600, border: "none" }}
            />
          ) : blobQ.data.mime.startsWith("text/") ? (
            <TextBlob url={blobQ.data.objectUrl} />
          ) : (
            <div>
              Formato non visualizzabile nel browser.{" "}
              <a href={blobQ.data.objectUrl} download>scarica il file</a>
            </div>
          )}

          <ChunksList
            documentId={documentId}
            session={session}
            highlightChunkId={highlightChunkId ?? null}
          />
        </div>
      )}
    </div>
  );
}

function ChunksList({
  documentId,
  session,
  highlightChunkId,
}: {
  documentId: string;
  session: Session;
  highlightChunkId: string | null;
}) {
  const chunks = useQuery({
    queryKey: ["chunks", documentId],
    queryFn: () =>
      apiFetch<Chunk[]>(`/v1/documents/${documentId}/chunks`, {}, session.token),
    refetchInterval: (q) => {
      const data = q.state.data as Chunk[] | undefined;
      return !data || data.length === 0 ? 3_000 : false;
    },
  });

  // Una sola query per tutto il documento al posto di N (una per chunk).
  // Solo i chunk con count > 0 attivano il rendering del badge.
  const reverseCounts = useQuery({
    queryKey: ["reverse-provenance-counts", documentId],
    queryFn: () =>
      apiFetch<{ counts_by_chunk: Record<string, number> }>(
        `/v1/documents/${documentId}/reverse-provenance-counts`,
        {},
        session.token,
      ),
    staleTime: 30_000,
  });

  // Auto-scroll al chunk evidenziato
  useEffect(() => {
    if (!highlightChunkId) return;
    const el = document.getElementById(`chunk-${highlightChunkId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlightChunkId, chunks.data]);

  if (chunks.isLoading) return <div style={{ padding: "0.75rem" }}>Cerco chunks…</div>;
  if (chunks.isError) return <div style={styles.error}>{String(chunks.error)}</div>;
  if (!chunks.data || chunks.data.length === 0) {
    return (
      <div style={{ marginTop: "1rem", padding: "0.75rem", background: "#fef3c7", color: "#78350f", borderRadius: 4, fontSize: "0.85rem" }}>
        Ingestion non ancora completata o documento non leggibile (formato non
        supportato).
      </div>
    );
  }

  return (
    <details style={{ marginTop: "1rem" }} open>
      <summary style={{ cursor: "pointer", fontWeight: 600, color: "#475569" }}>
        Chunks estratti ({chunks.data.length}) — il sistema li usera' per generare l'atto
      </summary>
      <ol style={{ paddingLeft: "1.5rem", marginTop: "0.5rem" }}>
        {chunks.data.map((c) => (
          <li
            key={c.id}
            id={`chunk-${c.id}`}
            style={{
              marginBottom: "0.75rem",
              background: highlightChunkId === c.id ? "#fef9c3" : "transparent",
              border: highlightChunkId === c.id ? "2px solid #facc15" : "none",
              padding: highlightChunkId === c.id ? "0.6rem" : 0,
              borderRadius: 4,
              transition: "background 200ms",
            }}
          >
            <ChunkLineageBadge
              chunkId={c.id}
              session={session}
              hint={reverseCounts.data?.counts_by_chunk[c.id] ?? 0}
            />
            <div style={{ fontSize: "0.72rem", color: "#94a3b8", marginBottom: "0.2rem" }}>
              chunk #{c.ordering}
              {c.page_number != null && ` · pag. ${c.page_number}`}
              {" · "}offset {c.char_start}-{c.char_end}
              {c.embedding_indexed ? " · ✓ indicizzato" : " · vector ko"}
              {c.token_count != null && ` · ~${c.token_count} token`}
              {" · class: "}<span style={{ color: classStatusColor(c.classification_status) }}>{c.classification_status}</span>
            </div>
            <div
              style={{
                background: "white",
                border: "1px solid #e2e8f0",
                padding: "0.5rem 0.75rem",
                borderRadius: 3,
                fontSize: "0.88rem",
                lineHeight: 1.5,
                whiteSpace: "pre-wrap",
              }}
            >
              {c.text}
            </div>
            <ChunkClassificationDetails classification={c.classification} status={c.classification_status} />
          </li>
        ))}
      </ol>
    </details>
  );
}


type ReverseProvenanceItem = {
  id: string;
  output_document_id: string;
  output_section_id: string;
  relation: string;
  rationale: string | null;
  confidence: number;
};

function ChunkLineageBadge({
  chunkId,
  session,
  hint,
}: {
  chunkId: string;
  session: Session;
  // Numero di link totali noto dal parent (batch query). Se 0, niente badge
  // e niente network: skippiamo l'intera query dettaglio.
  hint: number;
}) {
  const reverse = useQuery({
    queryKey: ["reverse-provenance", chunkId],
    queryFn: () =>
      apiFetch<{ uses: ReverseProvenanceItem[]; count: number }>(
        `/v1/documents/chunks/${chunkId}/reverse-provenance`,
        {},
        session.token,
      ),
    staleTime: 30_000,
    enabled: hint > 0,
  });

  if (hint === 0) return null;
  if (!reverse.data || reverse.data.count === 0) return null;

  // Raggruppa per output_document_id
  const grouped: Record<string, ReverseProvenanceItem[]> = {};
  for (const item of reverse.data.uses) {
    (grouped[item.output_document_id] ||= []).push(item);
  }

  return (
    <details
      style={{
        marginBottom: "0.4rem",
        padding: "0.35rem 0.6rem",
        background: "#ecfdf5",
        border: "1px solid #6ee7b7",
        borderRadius: 4,
      }}
    >
      <summary style={{ cursor: "pointer", fontSize: "0.78rem", color: "#065f46", fontWeight: 600 }}>
        ↗ Questo chunk e' usato in {reverse.data.count} sezion{reverse.data.count === 1 ? "e" : "i"} dell'atto generato
      </summary>
      <ul style={{ paddingLeft: "1rem", margin: "0.4rem 0", listStyle: "none" }}>
        {Object.entries(grouped).map(([docId, items]) => (
          <li key={docId} style={{ marginBottom: "0.4rem" }}>
            <div style={{ fontSize: "0.72rem", color: "#475569", marginBottom: "0.2rem" }}>
              Atto: <code>{docId.slice(0, 8)}…</code>
            </div>
            <ul style={{ paddingLeft: "1rem", margin: 0, listStyle: "disc" }}>
              {items.map((it) => (
                <li key={it.id} style={{ fontSize: "0.78rem", color: "#1f2937", marginBottom: "0.2rem" }}>
                  Sezione <strong>{it.output_section_id}</strong>
                  {" · "}
                  <code style={{ fontSize: "0.68rem", background: "#f3f4f6", padding: "0 0.3rem", borderRadius: 2 }}>
                    {it.relation}
                  </code>
                  {it.rationale && (
                    <span style={{ color: "#6b7280" }}> — {it.rationale}</span>
                  )}
                  <span style={{ color: "#9ca3af", fontSize: "0.7rem", marginLeft: "0.3rem" }}>
                    (conf {(it.confidence * 100).toFixed(0)}%)
                  </span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </details>
  );
}

function classStatusColor(s: Chunk["classification_status"]): string {
  if (s === "done") return "#166534";
  if (s === "abstained") return "#854d0e";
  if (s === "failed") return "#7f1d1d";
  return "#64748b";
}

function ChunkClassificationDetails({
  classification,
  status,
}: {
  classification: ChunkClassification | null;
  status: Chunk["classification_status"];
}) {
  if (!classification) {
    if (status === "in_progress" || status === "pending") {
      return <div style={{ marginTop: "0.4rem", fontSize: "0.78rem", color: "#64748b" }}>Sto analizzando...</div>;
    }
    return null;
  }
  if (classification.error) {
    return (
      <div style={{ marginTop: "0.4rem", fontSize: "0.78rem", color: "#7f1d1d" }}>
        Errore: {classification.error}
      </div>
    );
  }
  if (classification.abstained) {
    return (
      <div style={{ marginTop: "0.4rem", fontSize: "0.78rem", color: "#854d0e", fontStyle: "italic" }}>
        Il sistema si e' astenuto dalla classificazione: {classification.abstain_reason ?? "motivo non specificato"}
      </div>
    );
  }
  return (
    <div style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
      {classification.document_type && (
        <div>
          <strong>Tipo:</strong>{" "}
          <span style={styles.classBadge}>{classification.document_type.replace(/_/g, " ")}</span>
        </div>
      )}
      {classification.summary && (
        <div style={{ marginTop: "0.3rem", color: "#334155" }}>
          <strong>Riassunto:</strong> {classification.summary}
        </div>
      )}
      {classification.entities && classification.entities.length > 0 && (
        <div style={{ marginTop: "0.3rem" }}>
          <strong>Entita' estratte:</strong>
          <ul style={{ paddingLeft: "1.2rem", margin: "0.2rem 0" }}>
            {classification.entities.map((e, i) => (
              <li key={i} style={{ fontSize: "0.82rem" }}>
                <code style={{ background: "#f1f5f9", padding: "0 0.3rem", borderRadius: 2 }}>{e.type}</code>{" "}
                {e.value}
                {e.confidence > 0 && (
                  <span style={{ color: "#94a3b8", fontSize: "0.72rem", marginLeft: "0.4rem" }}>
                    (conf {(e.confidence * 100).toFixed(0)}%)
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {classification.suggested_tags && classification.suggested_tags.length > 0 && (
        <div style={{ marginTop: "0.3rem", display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
          {classification.suggested_tags.map((t, i) => (
            <span key={i} style={{ ...styles.classBadge, background: "#fef3c7", color: "#78350f" }}>
              #{t}
            </span>
          ))}
        </div>
      )}
      {classification.source_refs && classification.source_refs.length > 0 && (
        <div style={{ marginTop: "0.3rem", fontSize: "0.78rem", color: "#475569" }}>
          <strong>Riferimenti normativi citati:</strong>{" "}
          {classification.source_refs.map((r) => r.citation).join(", ")}
        </div>
      )}
    </div>
  );
}


function TextBlob({ url }: { url: string }) {
  const q = useQuery({
    queryKey: ["text-blob", url],
    queryFn: async () => {
      const r = await fetch(url);
      return r.text();
    },
    staleTime: Infinity,
  });
  if (q.isLoading) return <div>Carico testo...</div>;
  return (
    <pre style={styles.textPreview}>{q.data}</pre>
  );
}

function humanSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

function mimeIcon(mime: string): string {
  if (mime === "application/pdf") return "📕";
  if (mime.startsWith("image/")) return "🖼";
  if (mime.startsWith("text/")) return "📝";
  if (mime.includes("word") || mime.includes("opendocument")) return "📄";
  return "📎";
}

const styles = {
  card: {
    background: "white",
    border: "1px solid #e2e8f0",
    borderRadius: 6,
    padding: "1rem 1.25rem",
    marginBottom: "1rem",
  } as React.CSSProperties,
  title: { margin: "0 0 0.25rem 0", fontSize: "1.1rem", color: "#0f172a" },
  help: { color: "#64748b", fontSize: "0.9rem", margin: "0 0 1rem 0" },
  subtitle: { margin: "0 0 0.5rem 0", fontSize: "0.95rem", color: "#1e293b" },
  count: { color: "#94a3b8", fontWeight: 400, fontSize: "0.85rem" } as React.CSSProperties,
  dropzone: {
    border: "2px dashed #cbd5e1",
    borderRadius: 6,
    padding: "1.25rem",
    textAlign: "center",
    transition: "background 100ms, border-color 100ms",
  } as React.CSSProperties,
  pickerBtn: {
    padding: "0.4rem 1rem",
    background: "#1e293b",
    color: "white",
    border: "none",
    borderRadius: 4,
    cursor: "pointer",
    fontSize: "0.9rem",
  } as React.CSSProperties,
  uploading: { marginTop: "0.5rem", color: "#1d4ed8", fontSize: "0.88rem" } as React.CSSProperties,
  error: {
    marginTop: "0.5rem",
    background: "#fee2e2",
    color: "#7f1d1d",
    padding: "0.4rem 0.6rem",
    borderRadius: 4,
    fontSize: "0.85rem",
  } as React.CSSProperties,
  emptyList: {
    padding: "0.75rem",
    color: "#94a3b8",
    fontSize: "0.88rem",
    background: "#f8fafc",
    borderRadius: 4,
  } as React.CSSProperties,
  list: { listStyle: "none", padding: 0, margin: 0 } as React.CSSProperties,
  docRow: {
    display: "flex",
    alignItems: "center",
    border: "1px solid #e2e8f0",
    borderRadius: 4,
    marginBottom: "0.4rem",
    background: "white",
  } as React.CSSProperties,
  docRowActive: { borderColor: "#3b82f6", background: "#eff6ff" } as React.CSSProperties,
  docMain: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    padding: "0.55rem 0.75rem",
    background: "transparent",
    border: "none",
    cursor: "pointer",
    textAlign: "left",
  } as React.CSSProperties,
  mimeIcon: { fontSize: "1.2rem" } as React.CSSProperties,
  docInfo: { display: "flex", flexDirection: "column", gap: "0.15rem" } as React.CSSProperties,
  docMeta: { fontSize: "0.78rem", color: "#64748b" } as React.CSSProperties,
  deleteBtn: {
    width: 32,
    height: 32,
    border: "none",
    background: "transparent",
    color: "#94a3b8",
    fontSize: "1.2rem",
    cursor: "pointer",
    marginRight: "0.4rem",
  } as React.CSSProperties,
  preview: {
    marginTop: "1rem",
    border: "1px solid #e2e8f0",
    borderRadius: 6,
    background: "#fafaf9",
  } as React.CSSProperties,
  previewHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "0.6rem 0.9rem",
    borderBottom: "1px solid #e2e8f0",
    background: "white",
  } as React.CSSProperties,
  previewClose: {
    border: "1px solid #cbd5e1",
    background: "white",
    padding: "0.3rem 0.7rem",
    borderRadius: 3,
    cursor: "pointer",
    fontSize: "0.85rem",
  } as React.CSSProperties,
  previewBody: { padding: "0.6rem" } as React.CSSProperties,
  textPreview: {
    background: "white",
    border: "1px solid #e7e5e4",
    padding: "0.75rem",
    borderRadius: 3,
    fontSize: "0.85rem",
    maxHeight: 500,
    overflow: "auto",
    whiteSpace: "pre-wrap",
  } as React.CSSProperties,
  classStrip: {
    display: "flex",
    flexWrap: "wrap",
    gap: "0.3rem",
    padding: "0 0.75rem 0.55rem 2.4rem",
  } as React.CSSProperties,
  classBadge: {
    background: "#f1f5f9",
    color: "#334155",
    padding: "0.1rem 0.5rem",
    borderRadius: 3,
    fontSize: "0.72rem",
    fontWeight: 500,
  } as React.CSSProperties,
  classMore: {
    color: "#64748b",
    fontSize: "0.72rem",
    fontStyle: "italic",
    padding: "0.1rem 0",
  } as React.CSSProperties,
};
