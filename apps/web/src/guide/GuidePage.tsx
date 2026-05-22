import { useMemo, useState } from "react";
import { CATEGORY_LABELS, GUIDE_SECTIONS, GuideSection } from "./content";
import { Markdown } from "./Markdown";

export function GuidePage() {
  const [activeSlug, setActiveSlug] = useState<string>(GUIDE_SECTIONS[0].slug);
  const [filter, setFilter] = useState("");

  const grouped = useMemo(() => {
    const filt = filter.trim().toLowerCase();
    const matches = (s: GuideSection) =>
      !filt ||
      s.title.toLowerCase().includes(filt) ||
      s.summary.toLowerCase().includes(filt) ||
      s.body.toLowerCase().includes(filt);

    const out: Record<string, GuideSection[]> = {};
    for (const s of GUIDE_SECTIONS) {
      if (!matches(s)) continue;
      (out[s.category] ||= []).push(s);
    }
    return out;
  }, [filter]);

  const active = GUIDE_SECTIONS.find((s) => s.slug === activeSlug) ?? GUIDE_SECTIONS[0];

  return (
    <div style={styles.wrapper}>
      <aside style={styles.sidebar}>
        <h2 style={styles.sidebarTitle}>Guida NotAI</h2>
        <input
          type="search"
          placeholder="Cerca nella guida..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={styles.search}
        />
        <nav>
          {Object.entries(grouped).map(([cat, sections]) => (
            <div key={cat} style={styles.categoryBlock}>
              <h3 style={styles.categoryHeader}>
                {CATEGORY_LABELS[cat as keyof typeof CATEGORY_LABELS] ?? cat}
              </h3>
              <ul style={styles.sectionList}>
                {sections.map((s) => (
                  <li key={s.slug}>
                    <button
                      onClick={() => setActiveSlug(s.slug)}
                      style={{
                        ...styles.sectionLink,
                        ...(s.slug === activeSlug ? styles.sectionLinkActive : {}),
                      }}
                    >
                      {s.title}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {Object.keys(grouped).length === 0 && (
            <div style={{ color: "#888", padding: "1rem 0" }}>Nessun risultato</div>
          )}
        </nav>
      </aside>

      <main style={styles.main}>
        <header style={styles.contentHeader}>
          <span style={styles.breadcrumb}>
            {CATEGORY_LABELS[active.category]} / <strong>{active.title}</strong>
          </span>
          <h1 style={styles.contentTitle}>{active.title}</h1>
          <p style={styles.contentSummary}>{active.summary}</p>
        </header>
        <article style={styles.article}>
          <Markdown body={active.body} />
        </article>
      </main>
    </div>
  );
}

const styles = {
  wrapper: {
    display: "grid",
    gridTemplateColumns: "260px 1fr",
    gap: "2rem",
    minHeight: "calc(100vh - 6rem)",
  } as React.CSSProperties,
  sidebar: {
    borderRight: "1px solid #e2e8f0",
    paddingRight: "1.5rem",
    position: "sticky",
    top: "1rem",
    alignSelf: "start",
    maxHeight: "calc(100vh - 2rem)",
    overflowY: "auto",
  } as React.CSSProperties,
  sidebarTitle: { fontSize: "1.1rem", marginBottom: "1rem", color: "#1a202c" },
  search: {
    width: "100%",
    padding: "0.4rem 0.6rem",
    border: "1px solid #cbd5e1",
    borderRadius: 4,
    fontSize: "0.9rem",
    marginBottom: "1.25rem",
  } as React.CSSProperties,
  categoryBlock: { marginBottom: "1rem" } as React.CSSProperties,
  categoryHeader: {
    fontSize: "0.75rem",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    color: "#64748b",
    marginBottom: "0.4rem",
  } as React.CSSProperties,
  sectionList: { listStyle: "none", padding: 0, margin: 0 } as React.CSSProperties,
  sectionLink: {
    display: "block",
    width: "100%",
    textAlign: "left",
    padding: "0.4rem 0.6rem",
    border: "none",
    background: "transparent",
    color: "#334155",
    fontSize: "0.9rem",
    cursor: "pointer",
    borderRadius: 4,
  } as React.CSSProperties,
  sectionLinkActive: {
    background: "#e0e7ff",
    color: "#1e3a8a",
    fontWeight: 600,
  } as React.CSSProperties,
  main: { paddingRight: "1rem" } as React.CSSProperties,
  contentHeader: {
    borderBottom: "1px solid #e2e8f0",
    paddingBottom: "1rem",
    marginBottom: "1.5rem",
  } as React.CSSProperties,
  breadcrumb: { fontSize: "0.85rem", color: "#64748b" } as React.CSSProperties,
  contentTitle: { fontSize: "2rem", margin: "0.5rem 0", color: "#0f172a" },
  contentSummary: { color: "#475569", fontSize: "1rem", margin: 0 },
  article: { maxWidth: "780px" } as React.CSSProperties,
};
