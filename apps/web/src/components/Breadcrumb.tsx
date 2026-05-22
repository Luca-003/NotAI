// Breadcrumb sempre visibile per pagine annidate (Pratica > Atto).
// I link sono <a href="#/..."> -> niente prevent default, il routing
// ascolta hashchange.

import type React from "react";

export type Crumb = {
  label: string;
  href?: string;  // se omesso e' il nodo "corrente" (no link, weight 600)
};

export function Breadcrumb({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <nav style={styles.bar} aria-label="breadcrumb">
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1;
        return (
          <span key={i} style={styles.item}>
            {!last && c.href ? (
              <a href={c.href} style={styles.link}>
                {c.label}
              </a>
            ) : (
              <span style={styles.current}>{c.label}</span>
            )}
            {!last && <span style={styles.sep}>›</span>}
          </span>
        );
      })}
    </nav>
  );
}

const styles = {
  bar: {
    display: "flex",
    alignItems: "center",
    gap: "0.4rem",
    fontSize: "0.85rem",
    color: "#64748b",
    marginBottom: "1rem",
    padding: "0.5rem 0.75rem",
    background: "#f1f5f9",
    borderRadius: 4,
  } as React.CSSProperties,
  item: { display: "inline-flex", alignItems: "center", gap: "0.4rem" } as React.CSSProperties,
  link: {
    color: "#1e293b",
    textDecoration: "none",
    fontWeight: 500,
  } as React.CSSProperties,
  current: { color: "#0f172a", fontWeight: 700 } as React.CSSProperties,
  sep: { color: "#cbd5e1" } as React.CSSProperties,
};
