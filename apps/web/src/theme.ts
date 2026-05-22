// Styles condivisi tra le pagine. Espande il pattern `s` di PracticesPage
// (gia' importato da ActDetail) con i 2-3 oggetti piu' duplicati.
//
// Strategia: non riscrivere tutto in una volta - aggiungi qui i nuovi
// shared styles man mano che servono. Cosi' eventuali divergenze visive
// vengono colte dalla review e non si propagano.

import type React from "react";

/** Card "panel" base usata in ~6 file. */
export const card: React.CSSProperties = {
  background: "white",
  border: "1px solid #e2e8f0",
  borderRadius: 6,
  padding: "1rem 1.25rem",
  marginBottom: "1rem",
};

/** Box rosso d'errore inline. */
export const errorBox: React.CSSProperties = {
  background: "#fee2e2",
  color: "#7f1d1d",
  padding: "0.5rem 0.75rem",
  borderRadius: 4,
  fontSize: "0.85rem",
};

/** Re-export per import unificato:  import { theme } from "../theme" */
export const theme = { card, errorBox };
