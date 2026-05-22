// Costanti per Document.kind, allineate con notai/contexts/documents/kinds.py.
// Tenute manualmente in sync: la backend non genera automaticamente il .ts
// (lo faremo con un piccolo tool quando il numero di enum cresce).

export const KIND_INPUT_SOURCE = "input_source";
export const KIND_ALLEGATO = "allegato";
export const KIND_ATTO_FIRMATO = "atto_firmato";
export const KIND_DRAFT = "draft";

export type DocumentKind =
  | typeof KIND_INPUT_SOURCE
  | typeof KIND_ALLEGATO
  | typeof KIND_ATTO_FIRMATO
  | typeof KIND_DRAFT
  | string; // tolleranza per kind non ancora promossi a costante

/** "Tutti gli input": include il principale + gli allegati. */
export const INPUT_KINDS: readonly string[] = [KIND_INPUT_SOURCE, KIND_ALLEGATO];

export function isInputKind(kind: string): boolean {
  return INPUT_KINDS.includes(kind);
}
