// Hook condivisi per query di provenance/lineage.
// Centralizzano i 4 endpoint usati da DraftViewer, LineageGraph, ChunkLineageBadge.

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../auth";

export type ProvLink = {
  id: string;
  source_chunk_id: string;
  source_document_id: string;
  relation: string;
  rationale: string | null;
  confidence: number;
};

export type ReverseProvenanceItem = {
  id: string;
  output_document_id: string;
  output_section_id: string;
  relation: string;
  rationale: string | null;
  confidence: number;
};

/** Per ciascuna sezione dell'atto, lista dei chunk sorgenti che la giustificano. */
export function useDocumentProvenance(documentId: string, token: string) {
  return useQuery({
    queryKey: ["doc-provenance", documentId],
    queryFn: () =>
      apiFetch<{ links_by_section: Record<string, ProvLink[]>; total_links: number }>(
        `/v1/documents/${documentId}/provenance`,
        {},
        token,
      ),
  });
}

/** Conteggio aggregato dei link in uscita per ogni chunk del documento di input. */
export function useReverseProvenanceCounts(documentId: string, token: string) {
  return useQuery({
    queryKey: ["reverse-provenance-counts", documentId],
    queryFn: () =>
      apiFetch<{ counts_by_chunk: Record<string, number> }>(
        `/v1/documents/${documentId}/reverse-provenance-counts`,
        {},
        token,
      ),
    staleTime: 30_000,
  });
}

/** Dettaglio degli atti che hanno usato un chunk specifico (per ChunkLineageBadge). */
export function useChunkReverseProvenance(
  chunkId: string,
  token: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["reverse-provenance", chunkId],
    queryFn: () =>
      apiFetch<{ uses: ReverseProvenanceItem[]; count: number }>(
        `/v1/documents/chunks/${chunkId}/reverse-provenance`,
        {},
        token,
      ),
    staleTime: 30_000,
    enabled,
  });
}
