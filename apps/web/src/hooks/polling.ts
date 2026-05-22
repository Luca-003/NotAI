// Helpers per il pattern "polla finche' la query soddisfa una condizione".
//
// TanStack Query accetta `refetchInterval: (q) => number | false`. Lo usavamo
// con 4 closure quasi identiche ("polla a Ns finche' data non e' pronto", etc).
// Qui le centralizziamo per leggibilita' e coerenza.

import type { Query } from "@tanstack/react-query";

/**
 * Ritorna un predicate `refetchInterval` che:
 *   - polla a `whileMs` finche' `isStillWorking(data)` e' true (o data e' undefined)
 *   - smette di pollare (`false`) quando il lavoro e' finito
 *
 * `whileMs` default 3000 (3s). Sotto questo valore si rischia di saturare
 * un'API piccola; sopra 5s l'utente percepisce ritardo nel feedback.
 */
export function pollWhile<T>(
  isStillWorking: (data: T | undefined) => boolean,
  whileMs: number = 3_000,
): (q: Query) => number | false {
  return (q) => {
    const data = q.state.data as T | undefined;
    return isStillWorking(data) ? whileMs : false;
  };
}
