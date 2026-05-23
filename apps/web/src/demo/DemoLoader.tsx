// Bottone "Carica scenari demo": crea 6 pratiche (3 notarile + 3 legale)
// con 1 atto ciascuna via API REST. Da usare dopo "Accedi (dev)" in topbar.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, type Session } from "../auth";
import { buildHref, type Tab } from "../routing";
import { DEMO_SCENARIOS, type DemoScenario } from "./scenarios";

type LoadedScenario = {
  scenario: DemoScenario;
  practice_id: string;
  act_id: string;
};

export function DemoLoader({
  session,
  goto,
}: {
  session: Session | null;
  goto: (tab: Tab, opts?: { practiceId?: string; actId?: string }) => void;
}) {
  const qc = useQueryClient();
  const [loaded, setLoaded] = useState<LoadedScenario[]>([]);

  const load = useMutation({
    mutationFn: async (): Promise<LoadedScenario[]> => {
      if (!session) throw new Error("Devi prima accedere (button in topbar)");
      const results: LoadedScenario[] = [];
      for (const sc of DEMO_SCENARIOS) {
        // 1. Crea pratica
        const practice = await apiFetch<{ id: string }>(
          "/v1/practices",
          {
            method: "POST",
            body: JSON.stringify(sc.practice),
          },
          session.token,
        );
        // 2. Crea atto associato
        const act = await apiFetch<{ id: string }>(
          "/v1/acts",
          {
            method: "POST",
            body: JSON.stringify({
              ...sc.act,
              practice_id: practice.id,
            }),
          },
          session.token,
        );

        // 3. Auto-upload dei documenti del case-study corrispondente.
        // Cosi' l'utente apre l'atto e trova gia' tutto pronto per classificare.
        // Best-effort: se l'endpoint dev/scenarios non e' disponibile o lo
        // scenario non ha case-study, andiamo avanti senza errore.
        try {
          await apiFetch(
            `/v1/dev/scenarios/${sc.id}/upload-to-act/${act.id}`,
            { method: "POST" },
            session.token,
          );
        } catch (e) {
          console.warn(`Upload demo docs failed per ${sc.id}:`, e);
        }

        results.push({ scenario: sc, practice_id: practice.id, act_id: act.id });
      }
      return results;
    },
    onSuccess: (res) => {
      setLoaded(res);
      qc.invalidateQueries({ queryKey: ["practices"] });
      qc.invalidateQueries({ queryKey: ["workspace-tree"] });
    },
  });

  return (
    <section style={styles.card}>
      <div style={styles.header}>
        <div>
          <h3 style={styles.title}>Carica scenari demo</h3>
          <p style={styles.help}>
            Crea 6 pratiche di esempio (3 notarile: compravendita, donazione,
            costituzione SRL · 3 legale: citazione, decreto ingiuntivo,
            separazione consensuale) <strong>con i documenti gia' caricati</strong>.
            Apri un atto e vedrai parsing + classificazione LLM in corso.
          </p>
        </div>
        <button
          onClick={() => load.mutate()}
          disabled={load.isPending || !session}
          style={styles.button}
        >
          {load.isPending ? "Caricamento..." : `Carica ${DEMO_SCENARIOS.length} scenari`}
        </button>
      </div>

      {!session && (
        <div style={styles.warning}>
          Devi prima fare login (bottone verde "Accedi (dev)" in alto a destra).
        </div>
      )}

      {load.isError && (
        <div style={styles.error}>Errore: {String(load.error)}</div>
      )}

      {loaded.length > 0 && (
        <div style={styles.result}>
          <strong>Pratiche create:</strong>
          <div style={{ display: "grid", gap: "0.5rem", marginTop: "0.75rem" }}>
            {loaded.map((l) => (
              <div key={l.act_id} style={styles.loadedCard}>
                <div style={{ flex: 1 }}>
                  <strong>{l.scenario.label}</strong>
                  <div style={{ fontSize: "0.78rem", color: "#475569", marginTop: "0.15rem" }}>
                    <code style={styles.id}>{l.scenario.practice.code}</code>{" "}
                    · {l.scenario.workflow_input.parties.length} parti
                  </div>
                </div>
                <a
                  href={buildHref("practices", { practiceId: l.practice_id, actId: l.act_id })}
                  style={styles.openBtn}
                >
                  Apri atto →
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      <details style={styles.preview}>
        <summary style={{ cursor: "pointer", fontWeight: 600, color: "#475569" }}>
          Cosa contengono gli scenari? ({DEMO_SCENARIOS.length})
        </summary>
        <ul style={{ marginTop: "0.75rem" }}>
          {DEMO_SCENARIOS.map((sc) => (
            <li key={sc.id} style={{ marginBottom: "0.6rem" }}>
              <strong>{sc.label}</strong>
              <div style={{ fontSize: "0.85rem", color: "#64748b", marginTop: "0.2rem" }}>
                base imponibile: <strong>{sc.workflow_input.base_imponibile.toLocaleString("it-IT")} €</strong>
                {sc.workflow_input.is_prima_casa && " · prima casa"}
                {" · "}
                {sc.workflow_input.parties.length} parti ({sc.workflow_input.parties.map((p) => p.role).join(", ")})
              </div>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}

const styles = {
  card: {
    background: "#fff7ed",
    border: "1px solid #fed7aa",
    borderLeft: "4px solid #f97316",
    borderRadius: 6,
    padding: "1rem 1.25rem",
    marginTop: "2rem",
  } as React.CSSProperties,
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: "1.5rem",
    marginBottom: "0.5rem",
  } as React.CSSProperties,
  title: { margin: 0, fontSize: "1.05rem", color: "#9a3412" },
  help: { color: "#7c2d12", fontSize: "0.9rem", margin: "0.25rem 0 0" },
  button: {
    padding: "0.6rem 1.25rem",
    background: "#ea580c",
    color: "white",
    border: "none",
    borderRadius: 4,
    cursor: "pointer",
    fontWeight: 600,
    whiteSpace: "nowrap",
  } as React.CSSProperties,
  warning: {
    marginTop: "0.75rem",
    background: "#fef3c7",
    color: "#854d0e",
    padding: "0.5rem 0.75rem",
    borderRadius: 4,
    fontSize: "0.85rem",
  } as React.CSSProperties,
  error: {
    marginTop: "0.75rem",
    background: "#fee2e2",
    color: "#7f1d1d",
    padding: "0.5rem 0.75rem",
    borderRadius: 4,
    fontSize: "0.85rem",
  } as React.CSSProperties,
  result: {
    marginTop: "0.75rem",
    background: "#dcfce7",
    border: "1px solid #86efac",
    color: "#14532d",
    padding: "0.75rem 1rem",
    borderRadius: 4,
    fontSize: "0.9rem",
  } as React.CSSProperties,
  id: {
    fontSize: "0.78rem",
    background: "#f1f5f9",
    padding: "0.1rem 0.4rem",
    borderRadius: 3,
    color: "#475569",
  } as React.CSSProperties,
  preview: { marginTop: "1rem", fontSize: "0.9rem" } as React.CSSProperties,
  loadedCard: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    background: "white",
    border: "1px solid #86efac",
    borderRadius: 4,
    padding: "0.6rem 0.8rem",
    gap: "1rem",
  } as React.CSSProperties,
  openBtn: {
    background: "#16a34a",
    color: "white",
    padding: "0.45rem 0.9rem",
    borderRadius: 4,
    textDecoration: "none",
    fontWeight: 600,
    fontSize: "0.88rem",
    whiteSpace: "nowrap",
  } as React.CSSProperties,
};
