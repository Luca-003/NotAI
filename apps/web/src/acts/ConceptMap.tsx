// Mappa concettuale del lineage atto -> sezioni -> chunk -> documenti sorgente.
// Usa mermaid per layout automatico graph TD (top-down) + drill-down click.
//
// Differenza con LineageGraph (SVG manuale): qui le sezioni si raggruppano
// gerarchicamente e i nodi sono espandibili (chunk -> entity types -> text snippet).

import mermaid from "mermaid";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../auth";

mermaid.initialize({
  startOnLoad: false,
  theme: "default",
  flowchart: { useMaxWidth: true, htmlLabels: true, curve: "basis" },
  themeVariables: {
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
    fontSize: "12px",
  },
});

type LineageNode = {
  input_documents: { id: string; filename: string; kind: string }[];
  chunks: {
    id: string;
    document_id: string;
    ordering: number;
    page_number: number | null;
    preview: string;
    entity_type?: string | null;
    document_type?: string | null;
  }[];
  output_sections: { id: string; title: string }[];
  edges: {
    id: string;
    source_chunk_id: string;
    output_section_id: string;
    relation: string;
    confidence: number;
    rationale: string | null;
  }[];
};

type ViewMode = "compact" | "expanded";

export function ConceptMap({
  documentId,
  token,
  onSelectChunk,
}: {
  documentId: string;
  token: string;
  onSelectChunk?: (sourceDocumentId: string, chunkId: string) => void;
}) {
  const [mode, setMode] = useState<ViewMode>("compact");

  const lineage = useQuery({
    queryKey: ["doc-lineage", documentId],
    queryFn: () =>
      apiFetch<LineageNode>(`/v1/documents/${documentId}/lineage`, {}, token),
  });

  const mermaidCode = useMemo(() => {
    if (!lineage.data) return "";
    return mode === "compact"
      ? renderCompact(lineage.data)
      : renderExpanded(lineage.data);
  }, [lineage.data, mode]);

  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    async function render() {
      if (!containerRef.current || !mermaidCode) return;
      try {
        // Mermaid 11.x ha API async: renderAsync(id, code) -> {svg, ...}
        const id = `mm-${documentId.slice(0, 8)}-${mode}`;
        const result = await mermaid.render(id, mermaidCode);
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = result.svg;
        // bind click handler ai nodi (chunk_XXX, doc_XXX) per drill-down
        result.bindFunctions?.(containerRef.current);
        if (onSelectChunk) {
          containerRef.current.querySelectorAll<SVGElement>("[id^='chunk_']").forEach((el) => {
            const nodeId = el.id.replace(/^.*chunk_/, "chunk_");
            const chunkId = nodeId.replace("chunk_", "");
            const chunk = lineage.data?.chunks.find((c) => c.id.startsWith(chunkId));
            if (!chunk) return;
            el.style.cursor = "pointer";
            el.addEventListener("click", () => onSelectChunk(chunk.document_id, chunk.id));
          });
        }
      } catch (e) {
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = `<div style="color:#b91c1c;padding:1rem;">Errore rendering mermaid: ${String(e)}</div>`;
        }
      }
    }
    render();
    return () => {
      cancelled = true;
    };
  }, [mermaidCode, documentId, mode, onSelectChunk, lineage.data]);

  if (lineage.isLoading) return <div style={{ padding: "1rem" }}>Carico lineage…</div>;
  if (lineage.isError) {
    return (
      <div style={{ padding: "0.6rem 0.8rem", background: "#fee2e2", color: "#7f1d1d", borderRadius: 4 }}>
        Errore lineage: {String(lineage.error)}
      </div>
    );
  }
  if (!lineage.data) return null;
  if (lineage.data.edges.length === 0) {
    return (
      <div style={{ padding: "1rem", color: "#94a3b8", fontStyle: "italic" }}>
        Nessun link di provenance: non c'e' niente da visualizzare.
      </div>
    );
  }

  return (
    <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 4 }}>
      <div style={{
        padding: "0.5rem 0.8rem", borderBottom: "1px solid #e2e8f0",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <strong style={{ fontSize: "0.85rem" }}>Mappa concettuale</strong>
        <div style={{ display: "flex", gap: "0.3rem" }}>
          <button
            onClick={() => setMode("compact")}
            style={{ ...btnStyle, ...(mode === "compact" ? activeStyle : {}) }}
          >
            Compatta
          </button>
          <button
            onClick={() => setMode("expanded")}
            style={{ ...btnStyle, ...(mode === "expanded" ? activeStyle : {}) }}
          >
            Espansa
          </button>
        </div>
      </div>
      <div ref={containerRef} style={{ padding: "1rem", textAlign: "center", overflow: "auto", maxHeight: 700 }} />
      <div style={{
        padding: "0.4rem 0.8rem", borderTop: "1px solid #e2e8f0",
        fontSize: "0.78rem", color: "#64748b",
      }}>
        {onSelectChunk && "Click su un chunk (verde) per aprirlo nel workspace. "}
        Modalita' Compatta = doc input &rarr; sezione atto.
        Espansa = doc input &rarr; chunk &rarr; entity_type &rarr; sezione atto.
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mermaid code generators
// ---------------------------------------------------------------------------

function safe(s: string): string {
  return s.replace(/["\\]/g, "_").replace(/\n/g, " ").replace(/[<>]/g, "");
}

function shortId(id: string): string {
  return id.replace(/-/g, "").slice(0, 10);
}

function renderCompact(data: LineageNode): string {
  // doc_input --> section_output, raggruppato per source_document_id
  const lines: string[] = ["graph LR"];
  lines.push("classDef inputDoc fill:#1e293b,stroke:#0f172a,color:#fff");
  lines.push("classDef section fill:#fff7ed,stroke:#f97316,color:#7c2d12");

  // Nodi documenti input
  const docs = data.input_documents;
  for (const d of docs) {
    const nid = `doc_${shortId(d.id)}`;
    lines.push(`${nid}["📄 ${safe(d.filename)}"]:::inputDoc`);
  }

  // Nodi sezioni
  for (const s of data.output_sections) {
    const nid = `sec_${safe(s.id)}`;
    lines.push(`${nid}["§ ${safe(s.title)}"]:::section`);
  }

  // Archi aggregati: doc -> sezione (raggruppa tramite chunks)
  const chunkToDoc: Record<string, string> = {};
  for (const c of data.chunks) chunkToDoc[c.id] = c.document_id;
  const seen = new Set<string>();
  for (const e of data.edges) {
    const docId = chunkToDoc[e.source_chunk_id];
    if (!docId) continue;
    const key = `${docId}__${e.output_section_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const dnid = `doc_${shortId(docId)}`;
    const snid = `sec_${safe(e.output_section_id)}`;
    lines.push(`${dnid} --> ${snid}`);
  }

  return lines.join("\n");
}

function renderExpanded(data: LineageNode): string {
  // doc -> chunk -> section, con stili distinti
  const lines: string[] = ["graph LR"];
  lines.push("classDef inputDoc fill:#1e293b,stroke:#0f172a,color:#fff,rx:6,ry:6");
  lines.push("classDef chunk fill:#dcfce7,stroke:#16a34a,color:#14532d,rx:4,ry:4");
  lines.push("classDef section fill:#fff7ed,stroke:#f97316,color:#7c2d12,rx:6,ry:6");

  // Nodi documenti input
  for (const d of data.input_documents) {
    const nid = `doc_${shortId(d.id)}`;
    lines.push(`${nid}["📄 ${safe(d.filename)}"]:::inputDoc`);
  }

  // Nodi chunk (solo quelli referenziati da almeno 1 edge)
  const referencedChunkIds = new Set(data.edges.map((e) => e.source_chunk_id));
  const chunks = data.chunks.filter((c) => referencedChunkIds.has(c.id));
  for (const c of chunks) {
    const nid = `chunk_${shortId(c.id)}`;
    const tag = c.entity_type || c.document_type || "";
    const label = `#${c.ordering}${tag ? ` · ${safe(tag)}` : ""}<br/>${safe(c.preview.slice(0, 40))}…`;
    lines.push(`${nid}["${label}"]:::chunk`);
    // Arco doc -> chunk
    const dnid = `doc_${shortId(c.document_id)}`;
    lines.push(`${dnid} --> ${nid}`);
  }

  // Sezioni e archi chunk -> sezione
  const referencedSectionIds = new Set(data.edges.map((e) => e.output_section_id));
  for (const s of data.output_sections.filter((s) => referencedSectionIds.has(s.id))) {
    const nid = `sec_${safe(s.id)}`;
    lines.push(`${nid}["§ ${safe(s.title)}"]:::section`);
  }
  for (const e of data.edges) {
    const cnid = `chunk_${shortId(e.source_chunk_id)}`;
    const snid = `sec_${safe(e.output_section_id)}`;
    const label = `${safe(e.relation)} ${(e.confidence * 100).toFixed(0)}%`;
    lines.push(`${cnid} -- "${label}" --> ${snid}`);
  }

  return lines.join("\n");
}

import type React from "react";
const btnStyle: React.CSSProperties = {
  padding: "0.25rem 0.65rem",
  fontSize: "0.78rem",
  background: "white",
  border: "1px solid #cbd5e1",
  borderRadius: 3,
  cursor: "pointer",
  color: "#475569",
};
const activeStyle: React.CSSProperties = {
  background: "#1e293b",
  color: "white",
  borderColor: "#0f172a",
};
