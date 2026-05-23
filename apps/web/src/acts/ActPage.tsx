// ActPage: wrapper che decide tra ActPreparation e ActDetail in base
// allo stato dell'atto.
//   - Workflow non avviato + non consolidato -> ActPreparation
//   - Workflow non avviato + consolidato -> ActPreparation con bottone "Procedi"
//   - Workflow avviato -> ActDetail (vista corrente con bozza+visure+review)

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, type Session } from "../auth";
import { Breadcrumb } from "../components/Breadcrumb";
import { buildHref, type Tab } from "../routing";
import { ActDetail } from "./ActDetail";
import { ActPreparation } from "./ActPreparation";
import { s } from "../practices/PracticesPage";

type Act = {
  id: string;
  practice_id: string;
  kind: string;
  title: string;
  workflow_status: string;
  workflow_run_id: string | null;
};

export function ActPage({
  session,
  actId,
  practiceTitle,
  practiceId,
  goto,
}: {
  session: Session;
  actId: string;
  practiceTitle: string;
  practiceId: string;
  goto: (tab: Tab, opts?: { practiceId?: string; actId?: string }) => void;
}) {
  const qc = useQueryClient();
  const act = useQuery({
    queryKey: ["act", actId],
    queryFn: () => apiFetch<Act>(`/v1/acts/${actId}`, {}, session.token),
  });

  // Avvio del workflow di generazione (compravendita ha imponibile dal slot
  // extractor; pero' il form richiede comunque parties+base_imponibile come
  // fallback). Per la demo: usiamo i default suggeriti dallo scenario; in
  // Fase 5 il form proviene dalla pratica.
  const start = useMutation({
    mutationFn: () =>
      apiFetch(
        `/v1/acts/${actId}/workflow/start`,
        {
          method: "POST",
          body: JSON.stringify({
            template_id: `${act.data?.kind}:v1`,
            base_imponibile: 250000,
            is_prima_casa: true,
            parties: [
              { role: "venditore", kind: "PF", fiscal_code: "RSSMRA70A01F205X" },
              { role: "acquirente", kind: "PF", fiscal_code: "BNCLCA85B05H501Y" },
            ],
          }),
        },
        session.token,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["act", actId] });
      qc.invalidateQueries({ queryKey: ["preparation", actId] });
      qc.invalidateQueries({ queryKey: ["wf-status", actId] });
    },
  });

  if (act.isLoading) return <div style={{ padding: "1rem" }}>Carico atto...</div>;
  if (act.isError) {
    return <div style={s.error}>{String(act.error)}</div>;
  }
  if (!act.data) return null;

  const breadcrumb = (
    <Breadcrumb
      crumbs={[
        { label: "Pratiche", href: buildHref("practices") },
        { label: practiceTitle, href: buildHref("practices", { practiceId }) },
        { label: act.data.title },
      ]}
    />
  );

  // Se il workflow e' gia' partito -> ActDetail (vista corrente)
  if (act.data.workflow_run_id) {
    return (
      <div>
        {breadcrumb}
        <ActDetail
          session={session}
          actId={actId}
          practiceTitle={practiceTitle}
          practiceId={practiceId}
          goto={goto}
        />
      </div>
    );
  }

  // Altrimenti: fase di preparazione esplicita
  return (
    <div>
      {breadcrumb}
      <header style={{ marginBottom: "1rem" }}>
        <h1 style={{ margin: 0 }}>{act.data.title}</h1>
        <code style={{ ...s.kindBadge, fontSize: "0.78rem" }}>{act.data.kind}</code>
      </header>
      <ActPreparation
        session={session}
        actId={actId}
        onProceed={() => start.mutate()}
      />
      {start.isError && (
        <div style={{ ...s.error, marginTop: "1rem" }}>
          {String(start.error)}
        </div>
      )}
    </div>
  );
}
