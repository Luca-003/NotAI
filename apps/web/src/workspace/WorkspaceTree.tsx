// Sidebar tree del workspace: pratiche -> atti -> documenti.
// Click su un nodo cambia il deep-link (hash routing) -> il MainArea
// si adatta al tipo di nodo selezionato.

import { useQuery } from "@tanstack/react-query";
import { apiFetch, type Session } from "../auth";
import { buildHref, type Route } from "../routing";

type DocNode = {
  kind: "document";
  id: string;
  label: string;
  doc_kind: string;
  mime_type: string;
  ingestion_status: string;
  size_bytes: number;
};

type ActNode = {
  kind: "act";
  id: string;
  label: string;
  act_kind: string;
  workflow_status: string;
  workflow_run_id: string | null;
  documents: { inputs: DocNode[]; visure_auto: DocNode[]; outputs: DocNode[] };
  counts: { inputs: number; visure_auto: number; outputs: number };
};

type PracticeNode = {
  kind: "practice";
  id: string;
  label: string;
  code: string;
  practice_kind: string;
  status: string;
  acts: ActNode[];
};

type TreeResponse = { practices: PracticeNode[]; practice_count: number };

export function WorkspaceTree({
  session,
  route,
}: {
  session: Session;
  route: Route;
}) {
  const tree = useQuery({
    queryKey: ["workspace-tree", session.token],
    queryFn: () => apiFetch<TreeResponse>("/v1/workspace/tree", {}, session.token),
    refetchInterval: 5_000,
  });

  return (
    <aside style={styles.sidebar}>
      <div style={styles.sidebarHeader}>
        <strong style={{ fontSize: "0.78rem", letterSpacing: 0.5, color: "#94a3b8" }}>
          WORKSPACE
        </strong>
        <a href={buildHref("dashboard")} style={styles.headerLink}>
          + nuova pratica
        </a>
      </div>

      {tree.isLoading && <div style={styles.empty}>Carico...</div>}
      {tree.isError && (
        <div style={styles.empty}>Errore: {String(tree.error)}</div>
      )}
      {tree.data && tree.data.practice_count === 0 && (
        <div style={styles.empty}>
          <p style={{ margin: "0.5rem 0", color: "#cbd5e1", fontSize: "0.85rem" }}>
            Nessuna pratica. Vai alla <a href={buildHref("dashboard")} style={{ color: "#60a5fa" }}>Dashboard</a> e carica gli scenari demo, oppure crea una pratica nuova.
          </p>
        </div>
      )}
      {tree.data && tree.data.practices.map((p) => (
        <PracticeBranch key={p.id} practice={p} route={route} />
      ))}
    </aside>
  );
}

function PracticeBranch({ practice, route }: { practice: PracticeNode; route: Route }) {
  const isSelected = route.practiceId === practice.id && !route.actId;
  const isOpen = route.practiceId === practice.id || practice.acts.length > 0;
  return (
    <div style={styles.practiceBranch}>
      <a
        href={buildHref("practices", { practiceId: practice.id })}
        style={{
          ...styles.practiceLink,
          ...(isSelected ? styles.selected : {}),
        }}
        title={`${practice.code} - ${practice.practice_kind}`}
      >
        <span style={styles.icon}>{isOpen ? "▾" : "▸"}</span>
        <span style={styles.folderIcon}>📁</span>
        <span style={styles.label}>{truncate(practice.label, 32)}</span>
        <span style={styles.subtle}>{practice.code}</span>
      </a>
      {isOpen && practice.acts.length === 0 && (
        <div style={styles.emptyChild}>(nessun atto)</div>
      )}
      {isOpen && practice.acts.map((a) => (
        <ActBranch key={a.id} act={a} practiceId={practice.id} route={route} />
      ))}
    </div>
  );
}

function ActBranch({
  act,
  practiceId,
  route,
}: {
  act: ActNode;
  practiceId: string;
  route: Route;
}) {
  const isSelected = route.actId === act.id;
  const isOpen = route.actId === act.id;
  const totalDocs = act.counts.inputs + act.counts.visure_auto + act.counts.outputs;
  return (
    <div style={{ marginLeft: "1.25rem" }}>
      <a
        href={buildHref("practices", { practiceId, actId: act.id })}
        style={{
          ...styles.actLink,
          ...(isSelected ? styles.selected : {}),
        }}
        title={act.act_kind}
      >
        <span style={styles.icon}>{isOpen ? "▾" : "▸"}</span>
        <span style={styles.folderIcon}>📂</span>
        <span style={styles.label}>{truncate(act.label, 30)}</span>
        <span style={styles.statusBadge}>{shortStatus(act.workflow_status)}</span>
      </a>
      {isOpen && (
        <div style={{ marginLeft: "0.75rem", borderLeft: "1px solid #334155", paddingLeft: "0.5rem" }}>
          {totalDocs === 0 && <div style={styles.emptyChild}>(nessun documento)</div>}
          {act.documents.inputs.length > 0 && (
            <DocGroup label="Input cliente" docs={act.documents.inputs} />
          )}
          {act.documents.visure_auto.length > 0 && (
            <DocGroup label="Visure acquisite" docs={act.documents.visure_auto} />
          )}
          {act.documents.outputs.length > 0 && (
            <DocGroup label="Bozze / output" docs={act.documents.outputs} />
          )}
        </div>
      )}
    </div>
  );
}

function DocGroup({ label, docs }: { label: string; docs: DocNode[] }) {
  return (
    <div style={{ marginBottom: "0.3rem" }}>
      <div style={styles.groupLabel}>{label}</div>
      {docs.map((d) => (
        <div key={d.id} style={styles.docLink} title={`${d.doc_kind} · ${d.mime_type}`}>
          <span style={styles.docIcon}>{statusIcon(d.ingestion_status)}</span>
          <span style={styles.docLabel}>{truncate(d.label, 30)}</span>
        </div>
      ))}
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function shortStatus(s: string): string {
  if (s === "review_completed") return "firmato";
  if (s === "review_requested") return "review";
  if (s === "draft_generated") return "bozza";
  if (s === "draft_in_corso") return "draft…";
  if (s === "visure_in_corso") return "visure…";
  if (s === "tax_calculated") return "imposte";
  return s.slice(0, 8);
}

function statusIcon(s: string): string {
  if (s === "done") return "✓";
  if (s === "in_progress") return "◐";
  if (s === "failed") return "✗";
  return "·";
}

import type React from "react";
const styles = {
  sidebar: {
    width: 320,
    flexShrink: 0,
    background: "#0f172a",
    color: "#e2e8f0",
    padding: "0.5rem 0",
    overflowY: "auto",
    height: "100vh",
    fontSize: "0.86rem",
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
  } as React.CSSProperties,
  sidebarHeader: {
    padding: "0.5rem 0.9rem",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottom: "1px solid #1e293b",
    marginBottom: "0.3rem",
  } as React.CSSProperties,
  headerLink: {
    fontSize: "0.72rem",
    color: "#60a5fa",
    textDecoration: "none",
  } as React.CSSProperties,
  empty: { padding: "1rem 0.9rem", color: "#94a3b8", fontSize: "0.85rem" } as React.CSSProperties,
  practiceBranch: { marginBottom: "0.15rem" } as React.CSSProperties,
  practiceLink: {
    display: "flex",
    alignItems: "center",
    gap: "0.3rem",
    padding: "0.35rem 0.6rem",
    color: "#e2e8f0",
    textDecoration: "none",
    cursor: "pointer",
    borderRadius: 2,
  } as React.CSSProperties,
  actLink: {
    display: "flex",
    alignItems: "center",
    gap: "0.3rem",
    padding: "0.3rem 0.5rem",
    color: "#cbd5e1",
    textDecoration: "none",
    cursor: "pointer",
    borderRadius: 2,
    fontSize: "0.83rem",
  } as React.CSSProperties,
  selected: { background: "#1e3a5f", color: "white", fontWeight: 600 } as React.CSSProperties,
  icon: { fontSize: "0.7rem", color: "#64748b", width: 10 } as React.CSSProperties,
  folderIcon: { fontSize: "0.85rem" } as React.CSSProperties,
  label: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } as React.CSSProperties,
  subtle: { fontSize: "0.7rem", color: "#64748b" } as React.CSSProperties,
  statusBadge: {
    fontSize: "0.65rem",
    background: "#1e293b",
    color: "#94a3b8",
    padding: "0.05rem 0.35rem",
    borderRadius: 2,
  } as React.CSSProperties,
  emptyChild: { marginLeft: "1.4rem", color: "#475569", fontSize: "0.78rem", fontStyle: "italic", padding: "0.2rem 0" } as React.CSSProperties,
  groupLabel: { fontSize: "0.7rem", color: "#64748b", padding: "0.3rem 0 0.15rem", textTransform: "uppercase", letterSpacing: 0.5 } as React.CSSProperties,
  docLink: {
    display: "flex",
    alignItems: "center",
    gap: "0.3rem",
    padding: "0.15rem 0.3rem",
    color: "#cbd5e1",
    fontSize: "0.78rem",
  } as React.CSSProperties,
  docIcon: { width: 10, color: "#64748b" } as React.CSSProperties,
  docLabel: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } as React.CSSProperties,
};
