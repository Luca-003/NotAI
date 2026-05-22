// Renderer minimo per il sottoinsieme di markdown usato nelle guide.
// Supporta: ### titoli, **bold**, *italic*, `inline code`, ``` code blocks,
// liste con - o numerate, link [text](url).
// NON usiamo una dipendenza per evitare bloat in Fase 4. Per casi piu' complessi
// passeremo a react-markdown in Fase 5+.

import React from "react";

type InlineToken =
  | { kind: "text"; value: string }
  | { kind: "code"; value: string }
  | { kind: "bold"; value: string }
  | { kind: "italic"; value: string }
  | { kind: "link"; text: string; href: string };

function tokenizeInline(line: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  let i = 0;
  while (i < line.length) {
    // ``` non e' inline; gestito a livello blocchi
    if (line[i] === "`") {
      const end = line.indexOf("`", i + 1);
      if (end > -1) {
        tokens.push({ kind: "code", value: line.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (line.startsWith("**", i)) {
      const end = line.indexOf("**", i + 2);
      if (end > -1) {
        tokens.push({ kind: "bold", value: line.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    if (line[i] === "*") {
      const end = line.indexOf("*", i + 1);
      if (end > -1) {
        tokens.push({ kind: "italic", value: line.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    // [text](url)
    if (line[i] === "[") {
      const textEnd = line.indexOf("]", i + 1);
      if (textEnd > -1 && line[textEnd + 1] === "(") {
        const urlEnd = line.indexOf(")", textEnd + 2);
        if (urlEnd > -1) {
          tokens.push({
            kind: "link",
            text: line.slice(i + 1, textEnd),
            href: line.slice(textEnd + 2, urlEnd),
          });
          i = urlEnd + 1;
          continue;
        }
      }
    }
    // Plain char: aggrega in una stringa fino al prossimo marker
    let j = i;
    while (
      j < line.length &&
      line[j] !== "`" &&
      !line.startsWith("**", j) &&
      line[j] !== "*" &&
      line[j] !== "["
    ) {
      j++;
    }
    tokens.push({ kind: "text", value: line.slice(i, j) });
    i = j;
  }
  return tokens;
}

function renderInline(line: string, key: string | number): React.ReactNode {
  const tokens = tokenizeInline(line);
  return (
    <React.Fragment key={key}>
      {tokens.map((t, idx) => {
        switch (t.kind) {
          case "code":
            return (
              <code key={idx} style={styles.inlineCode}>
                {t.value}
              </code>
            );
          case "bold":
            return <strong key={idx}>{t.value}</strong>;
          case "italic":
            return <em key={idx}>{t.value}</em>;
          case "link":
            return (
              <a key={idx} href={t.href} target="_blank" rel="noreferrer" style={styles.link}>
                {t.text}
              </a>
            );
          default:
            return <React.Fragment key={idx}>{t.value}</React.Fragment>;
        }
      })}
    </React.Fragment>
  );
}

export function Markdown({ body }: { body: string }) {
  const lines = body.split("\n");
  const blocks: React.ReactNode[] = [];

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // Code block ```
    if (line.trim().startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        buf.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push(
        <pre key={blocks.length} style={styles.codeBlock}>
          {buf.join("\n")}
        </pre>,
      );
      continue;
    }

    // Headings
    const headMatch = line.match(/^(#{1,4})\s+(.*)/);
    if (headMatch) {
      const level = headMatch[1].length;
      const text = headMatch[2];
      const Tag = (`h${Math.min(level + 1, 6)}`) as keyof React.JSX.IntrinsicElements;
      blocks.push(
        React.createElement(
          Tag,
          { key: blocks.length, style: styles.heading[level - 1] },
          renderInline(text, "h"),
        ),
      );
      i++;
      continue;
    }

    // Unordered list
    if (line.match(/^\s*[-*]\s+/)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^\s*[-*]\s+/)) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={blocks.length} style={styles.list}>
          {items.map((it, idx) => (
            <li key={idx}>{renderInline(it, idx)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    // Ordered list
    if (line.match(/^\s*\d+\.\s+/)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^\s*\d+\.\s+/)) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      blocks.push(
        <ol key={blocks.length} style={styles.list}>
          {items.map((it, idx) => (
            <li key={idx}>{renderInline(it, idx)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    // Empty line
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph (aggrega righe consecutive fino a blank)
    const para: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].match(/^(#{1,4}|\s*[-*]\s+|\s*\d+\.\s+|```)/)
    ) {
      para.push(lines[i]);
      i++;
    }
    blocks.push(
      <p key={blocks.length} style={styles.paragraph}>
        {renderInline(para.join(" "), "p")}
      </p>,
    );
  }

  return <div>{blocks}</div>;
}

const styles = {
  paragraph: { lineHeight: 1.6, marginBottom: "1rem", color: "#222" } as React.CSSProperties,
  list: { lineHeight: 1.7, marginBottom: "1rem", paddingLeft: "1.5rem" } as React.CSSProperties,
  inlineCode: {
    background: "#f3f3f3",
    padding: "0.1rem 0.3rem",
    borderRadius: 3,
    fontFamily: "ui-monospace, Menlo, Consolas, monospace",
    fontSize: "0.9em",
  } as React.CSSProperties,
  codeBlock: {
    background: "#1e293b",
    color: "#e2e8f0",
    padding: "1rem",
    borderRadius: 6,
    overflowX: "auto",
    fontFamily: "ui-monospace, Menlo, Consolas, monospace",
    fontSize: "0.85em",
    marginBottom: "1rem",
  } as React.CSSProperties,
  link: { color: "#2b6cb0", textDecoration: "underline" } as React.CSSProperties,
  heading: [
    { fontSize: "1.8rem", marginTop: "1.5rem", marginBottom: "1rem", color: "#1a202c" },
    { fontSize: "1.4rem", marginTop: "1.5rem", marginBottom: "0.75rem", color: "#1a202c" },
    { fontSize: "1.15rem", marginTop: "1.25rem", marginBottom: "0.5rem", color: "#2d3748" },
    { fontSize: "1rem", marginTop: "1rem", marginBottom: "0.5rem", color: "#4a5568" },
  ] as React.CSSProperties[],
};
