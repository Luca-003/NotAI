// Workspace documenti per un atto: upload (drag-drop + picker), lista, preview.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
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
};

export function DocumentsWorkspace({
  session,
  actId,
}: {
  session: Session;
  actId: string;
}) {
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const docs = useQuery({
    queryKey: ["docs", actId],
    queryFn: () => apiFetch<Doc[]>(`/v1/acts/${actId}/documents`, {}, session.token),
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
      />

      <DocumentList
        title="Output prodotti dal sistema"
        docs={outputDocs}
        selectedId={selectedId}
        onSelect={setSelectedId}
        emptyMsg="L'atto bozza apparir&agrave; qui dopo aver avviato il workflow."
      />

      {selectedId && (
        <DocumentPreview
          documentId={selectedId}
          session={session}
          onClose={() => setSelectedId(null)}
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
}: {
  title: string;
  docs: Doc[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete?: (id: string) => void;
  emptyMsg: string;
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
              <button onClick={() => onSelect(d.id)} style={styles.docMain}>
                <span style={styles.mimeIcon}>{mimeIcon(d.mime_type)}</span>
                <span style={styles.docInfo}>
                  <strong style={{ fontSize: "0.92rem" }}>{d.filename}</strong>
                  <span style={styles.docMeta}>
                    {d.mime_type} · {humanSize(d.size_bytes)} ·{" "}
                    <code style={{ fontSize: "0.7rem" }}>{d.sha256.slice(0, 10)}…</code>
                  </span>
                </span>
              </button>
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

function DocumentPreview({
  documentId,
  session,
  onClose,
}: {
  documentId: string;
  session: Session;
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
};
