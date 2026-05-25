// Auth helper "auto-login" per ambiente dev.
//
// Al primo caricamento della UI:
//   - Se in localStorage c'e' un JWT non scaduto -> lo usa.
//   - Altrimenti chiama POST /api/v1/dev/bootstrap con uno slug deterministico
//     ("studio-demo") e salva il token. Il backend fa upsert sul tenant,
//     quindi il tenant resta lo stesso tra reload.
//
// Risultato: dopo il caricamento, ogni pagina vede gia' principal + token
// senza bisogno di form o copia-incolla.

import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
const TOKEN_KEY = "notai.jwt";
const TENANT_KEY = "notai.tenant_id";

/** Root del server (senza il `/api`). Per endpoint cross-cutting come `/health`, `/readyz`. */
export function rootUrl(): string {
  return API_BASE.replace(/\/api$/, "");
}

export const DEMO_SLUG = "studio-demo";

export type Session = {
  token: string;
  tenantId: string;
};

function decodeJwtPayload(token: string): { exp?: number; tenant_id?: string; sub?: string } | null {
  try {
    const [, payload] = token.split(".");
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return json;
  } catch {
    return null;
  }
}

function isTokenValid(token: string): boolean {
  const claims = decodeJwtPayload(token);
  if (!claims || !claims.exp) return false;
  // Considera valido se mancano almeno 60s alla scadenza.
  return claims.exp * 1000 - Date.now() > 60_000;
}

async function bootstrapDemo(): Promise<Session> {
  const r = await fetch(`${API_BASE}/v1/dev/bootstrap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      slug: DEMO_SLUG,
      name: "Studio Demo",
      kind: "misto",
      admin_email: "admin@studio-demo.test",
      admin_display_name: "Admin Demo",
    }),
  });
  if (!r.ok) throw new Error(`bootstrap failed: HTTP ${r.status}`);
  const data = (await r.json()) as { token: string; tenant_id: string };
  localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(TENANT_KEY, data.tenant_id);
  return { token: data.token, tenantId: data.tenant_id };
}

export function useSession() {
  const [session, setSession] = useState<Session | null>(() => {
    // Lettura iniziale sincrona da localStorage, niente network call automatica.
    const tok = localStorage.getItem(TOKEN_KEY);
    const tid = localStorage.getItem(TENANT_KEY);
    if (tok && tid && isTokenValid(tok)) return { token: tok, tenantId: tid };
    return null;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reagisce al 401 globale: pulisce stato + mostra errore "sessione scaduta".
  useEffect(() => {
    const onExpired = () => {
      setSession(null);
      setError("Sessione scaduta - clicca 'Accedi (dev)' per riavviare.");
    };
    window.addEventListener("notai:session-expired", onExpired);
    return () => window.removeEventListener("notai:session-expired", onExpired);
  }, []);

  // Auto-login con un click (chiamato dal button "Accedi")
  const login = async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await bootstrapDemo();
      setSession(s);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TENANT_KEY);
    setSession(null);
  };

  return { session, loading, error, login, logout };
}

// Wrapper fetch che inietta automaticamente il bearer token.
export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const t = token ?? localStorage.getItem(TOKEN_KEY);
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
    "Content-Type": "application/json",
  };
  if (t) headers.Authorization = `Bearer ${t}`;
  const r = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!r.ok) {
    // 401 = JWT scaduto/invalido. Pulisci sessione e forza re-login.
    // L'utente vedra' il bottone "Accedi (dev)" in topbar e il messaggio
    // sotto via window event (intercept ottimisticamente con un alert).
    if (r.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TENANT_KEY);
      // Notifica il resto dell'app: il listener di useSession reagisce.
      window.dispatchEvent(new CustomEvent("notai:session-expired"));
    }
    const txt = await r.text().catch(() => "");
    throw new Error(`${path}: ${r.status} ${txt}`);
  }
  return (await r.json()) as T;
}
