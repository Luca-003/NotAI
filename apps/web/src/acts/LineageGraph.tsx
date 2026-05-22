// SVG flow chart: input docs -> chunks -> output sections.
// Renders the full provenance graph from /v1/documents/{id}/lineage in one shot.

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

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

const COL_INPUT_X = 30;
const COL_CHUNK_X = 360;
const COL_SECTION_X = 720;
const NODE_W_INPUT = 260;
const NODE_W_CHUNK = 280;
const NODE_W_SECTION = 250;
const NODE_H = 44;
const V_GAP = 14;
const TOP_PAD = 30;

export function LineageGraph({
  documentId,
  token,
  onSelectChunk,
}: {
  documentId: string;
  token: string | null;
  onSelectChunk?: (sourceDocumentId: string, chunkId: string) => void;
}) {
  const [hoveredSection, setHoveredSection] = useState<string | null>(null);
  const [hoveredChunk, setHoveredChunk] = useState<string | null>(null);

  const lineage = useQuery({
    queryKey: ["doc-lineage", documentId],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/v1/documents/${documentId}/lineage`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()) as LineageNode;
    },
  });

  const layout = useMemo(() => {
    if (!lineage.data) return null;
    const { input_documents, chunks, output_sections, edges } = lineage.data;

    // y-positions for each column
    const inputY: Record<string, number> = {};
    input_documents.forEach((d, i) => {
      inputY[d.id] = TOP_PAD + i * (NODE_H + V_GAP * 2);
    });

    // chunks ordered by (document index, ordering)
    const sortedChunks = [...chunks].sort((a, b) => {
      const ai = input_documents.findIndex((d) => d.id === a.document_id);
      const bi = input_documents.findIndex((d) => d.id === b.document_id);
      if (ai !== bi) return ai - bi;
      return a.ordering - b.ordering;
    });
    const chunkY: Record<string, number> = {};
    sortedChunks.forEach((c, i) => {
      chunkY[c.id] = TOP_PAD + i * (NODE_H + V_GAP);
    });

    const sectionY: Record<string, number> = {};
    output_sections.forEach((s, i) => {
      sectionY[s.id] = TOP_PAD + i * (NODE_H + V_GAP);
    });

    const height = Math.max(
      TOP_PAD + input_documents.length * (NODE_H + V_GAP * 2),
      TOP_PAD + sortedChunks.length * (NODE_H + V_GAP),
      TOP_PAD + output_sections.length * (NODE_H + V_GAP),
      200,
    ) + 20;

    return { inputY, chunkY, sectionY, sortedChunks, edges, height };
  }, [lineage.data]);

  if (lineage.isLoading) {
    return <div style={{ padding: "1rem", color: "#64748b" }}>Carico lineage…</div>;
  }
  if (lineage.isError) {
    return (
      <div style={{ padding: "0.6rem 0.8rem", background: "#fee2e2", color: "#7f1d1d", borderRadius: 4 }}>
        Errore lineage: {String(lineage.error)}
      </div>
    );
  }
  if (!lineage.data || !layout) return null;

  if (lineage.data.edges.length === 0) {
    return (
      <div style={{ padding: "1rem", color: "#94a3b8", fontStyle: "italic" }}>
        Nessun link di provenance per questo documento (il workflow non ha ancora
        generato collegamenti agli input).
      </div>
    );
  }

  const { input_documents, chunks } = lineage.data;
  const { inputY, chunkY, sectionY, sortedChunks, edges, height } = layout;

  const docById = new Map(input_documents.map((d) => [d.id, d]));
  const chunkById = new Map(chunks.map((c) => [c.id, c]));

  const isEdgeActive = (e: { source_chunk_id: string; output_section_id: string }) => {
    if (hoveredSection && e.output_section_id === hoveredSection) return true;
    if (hoveredChunk && e.source_chunk_id === hoveredChunk) return true;
    return false;
  };
  const anyHover = hoveredSection !== null || hoveredChunk !== null;

  return (
    <div style={{ overflowX: "auto", background: "#fafaf9", borderRadius: 4, border: "1px solid #e7e5e4" }}>
      <svg
        width={COL_SECTION_X + NODE_W_SECTION + 30}
        height={height}
        style={{ display: "block", minWidth: 1000 }}
      >
        {/* column headers */}
        <text x={COL_INPUT_X} y={18} fontSize={11} fontWeight={700} fill="#475569">
          DOCUMENTI INPUT
        </text>
        <text x={COL_CHUNK_X} y={18} fontSize={11} fontWeight={700} fill="#475569">
          CHUNK (sezioni di testo estratte)
        </text>
        <text x={COL_SECTION_X} y={18} fontSize={11} fontWeight={700} fill="#475569">
          SEZIONI DELL&apos;ATTO
        </text>

        {/* edges first (so they sit behind nodes) */}
        {edges.map((e) => {
          const chY = chunkY[e.source_chunk_id];
          const secY = sectionY[e.output_section_id];
          if (chY === undefined || secY === undefined) return null;
          const x1 = COL_CHUNK_X + NODE_W_CHUNK;
          const y1 = chY + NODE_H / 2;
          const x2 = COL_SECTION_X;
          const y2 = secY + NODE_H / 2;
          const mx = (x1 + x2) / 2;
          const active = isEdgeActive(e);
          const stroke = active ? "#16a34a" : anyHover ? "#e5e5e5" : "#cbd5e1";
          const opacity = active ? 1 : anyHover ? 0.35 : 0.7;
          return (
            <path
              key={e.id}
              d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`}
              fill="none"
              stroke={stroke}
              strokeWidth={active ? 2.2 : 1.4}
              opacity={opacity}
            >
              <title>{e.relation} (conf {(e.confidence * 100).toFixed(0)}%) — {e.rationale ?? ""}</title>
            </path>
          );
        })}

        {/* edges input doc -> its chunks (light grey, decorative) */}
        {sortedChunks.map((c) => {
          const dy = inputY[c.document_id];
          if (dy === undefined) return null;
          const x1 = COL_INPUT_X + NODE_W_INPUT;
          const y1 = dy + NODE_H / 2;
          const x2 = COL_CHUNK_X;
          const y2 = chunkY[c.id] + NODE_H / 2;
          const mx = (x1 + x2) / 2;
          return (
            <path
              key={`grp-${c.id}`}
              d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`}
              fill="none"
              stroke="#e2e8f0"
              strokeWidth={1}
              strokeDasharray="3,3"
            />
          );
        })}

        {/* input documents */}
        {input_documents.map((d) => (
          <g key={d.id} transform={`translate(${COL_INPUT_X}, ${inputY[d.id]})`}>
            <rect
              width={NODE_W_INPUT}
              height={NODE_H}
              rx={4}
              fill="#1e293b"
              stroke="#0f172a"
            />
            <text x={10} y={18} fontSize={11} fill="#94a3b8" fontWeight={600}>
              {d.kind}
            </text>
            <text x={10} y={34} fontSize={12} fill="white" fontWeight={500}>
              {truncate(d.filename, 36)}
            </text>
          </g>
        ))}

        {/* chunks */}
        {sortedChunks.map((c) => {
          const d = docById.get(c.document_id);
          const isHover = hoveredChunk === c.id;
          const tag = c.entity_type || c.document_type || "";
          return (
            <g
              key={c.id}
              transform={`translate(${COL_CHUNK_X}, ${chunkY[c.id]})`}
              style={{ cursor: onSelectChunk ? "pointer" : "default" }}
              onMouseEnter={() => setHoveredChunk(c.id)}
              onMouseLeave={() => setHoveredChunk(null)}
              onClick={() => d && onSelectChunk?.(d.id, c.id)}
            >
              <rect
                width={NODE_W_CHUNK}
                height={NODE_H}
                rx={4}
                fill={isHover ? "#dcfce7" : "#fff"}
                stroke={isHover ? "#16a34a" : "#cbd5e1"}
                strokeWidth={isHover ? 1.8 : 1}
              />
              <text x={10} y={16} fontSize={10} fill="#64748b" fontWeight={600}>
                #{c.ordering}
                {c.page_number !== null && c.page_number !== undefined && ` · p.${c.page_number}`}
                {tag && ` · ${tag}`}
              </text>
              <text x={10} y={32} fontSize={11} fill="#1c1917">
                {truncate(c.preview, 42)}
              </text>
            </g>
          );
        })}

        {/* output sections */}
        {lineage.data.output_sections.map((s) => {
          const isHover = hoveredSection === s.id;
          return (
            <g
              key={s.id}
              transform={`translate(${COL_SECTION_X}, ${sectionY[s.id]})`}
              style={{ cursor: "pointer" }}
              onMouseEnter={() => setHoveredSection(s.id)}
              onMouseLeave={() => setHoveredSection(null)}
            >
              <rect
                width={NODE_W_SECTION}
                height={NODE_H}
                rx={4}
                fill={isHover ? "#fef3c7" : "#fff"}
                stroke={isHover ? "#f59e0b" : "#cbd5e1"}
                strokeWidth={isHover ? 1.8 : 1}
              />
              <text x={10} y={18} fontSize={10} fill="#64748b" fontWeight={600}>
                {s.id}
              </text>
              <text x={10} y={34} fontSize={12} fill="#1c1917" fontWeight={500}>
                {truncate(s.title, 32)}
              </text>
            </g>
          );
        })}
      </svg>

      <div style={{ padding: "0.5rem 1rem", fontSize: "0.78rem", color: "#64748b", borderTop: "1px solid #e7e5e4" }}>
        Passa il mouse su un nodo per isolare i suoi collegamenti.
        {onSelectChunk && " Clicca su un chunk per aprirlo nel workspace."}
        {" "}
        <strong>{edges.length}</strong> link · <strong>{chunks.length}</strong> chunk · <strong>{lineage.data.output_sections.length}</strong> sezioni.
      </div>
    </div>
  );
}

function truncate(s: string, n: number): string {
  if (!s) return "";
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
