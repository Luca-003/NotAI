// Helper di testo condivisi.

/** Tronca `s` a `n` char con ellipsi. Ritorna stringa vuota se input falsy. */
export function truncate(s: string | null | undefined, n: number): string {
  if (!s) return "";
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
