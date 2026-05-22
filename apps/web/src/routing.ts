// Routing minimale via URL hash. Niente react-router: una sola dipendenza in piu'
// per uno stack che gia' usa state locale + TanStack.
//
// URL pattern:
//   #/dashboard
//   #/practices
//   #/practices/<practice_id>
//   #/practices/<practice_id>/acts/<act_id>
//   #/wiki | #/modules | #/guide
//
// API:
//   useRoute() -> { tab, practiceId, actId, goto(tab, opts?) }
//   buildHref(tab, opts) -> string da usare in <a href>

import { useEffect, useState } from "react";

export type Tab = "dashboard" | "practices" | "wiki" | "guide" | "modules";

export type Route = {
  tab: Tab;
  practiceId: string | null;
  actId: string | null;
};

const DEFAULT_ROUTE: Route = { tab: "dashboard", practiceId: null, actId: null };

function parseHash(hash: string): Route {
  // togli "#/" iniziale
  const path = hash.replace(/^#\/?/, "");
  if (!path) return DEFAULT_ROUTE;
  const parts = path.split("/").filter(Boolean);
  const head = parts[0] as Tab;
  if (head === "practices") {
    return {
      tab: "practices",
      practiceId: parts[1] ?? null,
      actId: parts[2] === "acts" ? (parts[3] ?? null) : null,
    };
  }
  if (head === "dashboard" || head === "wiki" || head === "modules" || head === "guide") {
    return { ...DEFAULT_ROUTE, tab: head };
  }
  return DEFAULT_ROUTE;
}

export function buildHref(
  tab: Tab,
  opts?: { practiceId?: string; actId?: string },
): string {
  if (tab !== "practices" || !opts?.practiceId) return `#/${tab}`;
  if (opts.actId) return `#/practices/${opts.practiceId}/acts/${opts.actId}`;
  return `#/practices/${opts.practiceId}`;
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onHash = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const goto = (tab: Tab, opts?: { practiceId?: string; actId?: string }) => {
    const next = buildHref(tab, opts);
    if (next !== window.location.hash) {
      window.location.hash = next;
    } else {
      // forza un re-render quando l'utente clicca lo stesso link
      setRoute(parseHash(next));
    }
  };

  return { route, goto };
}
