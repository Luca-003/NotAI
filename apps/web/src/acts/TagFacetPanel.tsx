// Pannello facet: mostra tag, document_types, entity_types aggregati
// per l'atto. Click su una facet la rende "attiva" e filtra l'elenco
// chunk del workspace (filtro client-side per ora; in Fase 5+ server-side
// con query param).

import { useQuery } from "@tanstack/react-query";
import { apiFetch, type Session } from "../auth";

type TagsResponse = {
  act_id: string;
  tags: { name: string; count: number }[];
  document_types: { name: string; count: number; chunks: string[] }[];
  entity_types: { name: string; count: number }[];
  chunks_analyzed: number;
};

export type FacetFilter = {
  document_type: string | null;
  tag: string | null;
};

export const NO_FILTER: FacetFilter = { document_type: null, tag: null };

export function TagFacetPanel({
  actId,
  session,
  filter,
  setFilter,
}: {
  actId: string;
  session: Session;
  filter: FacetFilter;
  setFilter: (f: FacetFilter) => void;
}) {
  const q = useQuery({
    queryKey: ["act-tags", actId],
    queryFn: () =>
      apiFetch<TagsResponse>(`/v1/acts/${actId}/tags`, {}, session.token),
    staleTime: 15_000,
    refetchInterval: 10_000,
  });

  const data = q.data;
  if (!data || data.chunks_analyzed === 0) return null;

  const anyActive = filter.document_type || filter.tag;

  return (
    <aside style={styles.panel}>
      <header style={styles.header}>
        <strong style={{ fontSize: "0.78rem", letterSpacing: 0.5, color: "#64748b" }}>
          FACET
        </strong>
        {anyActive && (
          <button
            onClick={() => setFilter(NO_FILTER)}
            style={styles.clearBtn}
            title="Rimuovi tutti i filtri"
          >
            ✕ reset
          </button>
        )}
      </header>

      {data.document_types.length > 0 && (
        <FacetSection
          title="Tipo documento"
          items={data.document_types.map((d) => ({ name: d.name, count: d.count }))}
          activeName={filter.document_type}
          onToggle={(name) =>
            setFilter({ ...filter, document_type: filter.document_type === name ? null : name })
          }
        />
      )}

      {data.tags.length > 0 && (
        <FacetSection
          title="Tag"
          items={data.tags.slice(0, 20)}
          activeName={filter.tag}
          onToggle={(name) =>
            setFilter({ ...filter, tag: filter.tag === name ? null : name })
          }
        />
      )}

      {data.entity_types.length > 0 && (
        <FacetSection
          title="Tipi di entita' estratte"
          items={data.entity_types.slice(0, 15)}
          activeName={null}
          onToggle={() => {}}
          readonly
        />
      )}
    </aside>
  );
}

function FacetSection({
  title,
  items,
  activeName,
  onToggle,
  readonly = false,
}: {
  title: string;
  items: { name: string; count: number }[];
  activeName: string | null;
  onToggle: (name: string) => void;
  readonly?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <section style={{ marginBottom: "0.8rem" }}>
      <div style={styles.sectionLabel}>{title}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
        {items.map((it) => {
          const active = activeName === it.name;
          return (
            <button
              key={it.name}
              onClick={() => !readonly && onToggle(it.name)}
              style={{
                ...styles.chip,
                ...(readonly ? styles.chipReadonly : {}),
                ...(active ? styles.chipActive : {}),
              }}
              disabled={readonly}
              title={readonly ? "" : "Click per filtrare"}
            >
              {it.name}{" "}
              <span style={{ opacity: 0.6, fontSize: "0.72rem" }}>{it.count}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

import type React from "react";
const styles = {
  panel: {
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 6,
    padding: "0.75rem 1rem",
    marginBottom: "1rem",
  } as React.CSSProperties,
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "0.6rem",
  } as React.CSSProperties,
  clearBtn: {
    fontSize: "0.74rem",
    background: "white",
    border: "1px solid #cbd5e1",
    padding: "0.15rem 0.5rem",
    borderRadius: 3,
    cursor: "pointer",
    color: "#475569",
  } as React.CSSProperties,
  sectionLabel: {
    fontSize: "0.74rem",
    color: "#475569",
    fontWeight: 600,
    marginBottom: "0.3rem",
    textTransform: "uppercase",
    letterSpacing: 0.4,
  } as React.CSSProperties,
  chip: {
    background: "white",
    border: "1px solid #cbd5e1",
    borderRadius: 999,
    padding: "0.15rem 0.55rem",
    fontSize: "0.78rem",
    cursor: "pointer",
    color: "#1e293b",
  } as React.CSSProperties,
  chipActive: {
    background: "#1e293b",
    color: "white",
    borderColor: "#0f172a",
    fontWeight: 600,
  } as React.CSSProperties,
  chipReadonly: {
    cursor: "default",
    opacity: 0.8,
  } as React.CSSProperties,
};
