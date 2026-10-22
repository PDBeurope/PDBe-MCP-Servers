export interface ComparisonResidue {
  label_seq_id: number; auth_seq_id: number | null; insertion_code: string; comp_id: string;
}
export interface ComparisonSide {
  pdb_id: string; title: string; coordinate_url: string; entry_url: string;
  chain: { label_asym_id: string; auth_asym_id: string; entity_id: string; name: string };
  matrix: number[][]; cluster_indices: number[];
  model_id?: number;
}
export interface ComparisonPair {
  uniprot_position: number; reference: ComparisonResidue; mobile: ComparisonResidue;
}
export interface ComparisonData {
  reference: ComparisonSide; mobile: ComparisonSide; uniprot_accession: string;
  segment: { index: number; start: number; end: number }; pairs: ComparisonPair[];
  mapped_pair_count: number; method: string;
  sources: string[]; retrieved_at: string; warnings: string[];
}
/** Export source correspondence, identities and provenance without geometric scores. */
export function comparisonCsv(data: ComparisonData): string {
  const quote = (value: unknown) => {
    const text = String(value ?? "");
    const safe = typeof value === "string" && /^\s*[=+@-]/.test(text) ? `'${text}` : text;
    return `"${safe.replaceAll('"', '""')}"`;
  };
  const columns = ["uniprot_accession", "uniprot_position", "segment_index", "reference_pdb", "reference_label_chain", "reference_auth_chain", "reference_label_residue", "reference_auth_residue", "reference_insertion_code", "reference_comp_id", "mobile_pdb", "mobile_label_chain", "mobile_auth_chain", "mobile_label_residue", "mobile_auth_residue", "mobile_insertion_code", "mobile_comp_id", "reference_matrix_rows", "mobile_matrix_rows", "method", "sources", "retrieved_at"];
  return [columns, ...data.pairs.map(pair => [data.uniprot_accession, pair.uniprot_position, data.segment.index,
    data.reference.pdb_id, data.reference.chain.label_asym_id, data.reference.chain.auth_asym_id,
    pair.reference.label_seq_id, pair.reference.auth_seq_id, pair.reference.insertion_code, pair.reference.comp_id,
    data.mobile.pdb_id, data.mobile.chain.label_asym_id, data.mobile.chain.auth_asym_id,
    pair.mobile.label_seq_id, pair.mobile.auth_seq_id, pair.mobile.insertion_code, pair.mobile.comp_id,
    JSON.stringify(data.reference.matrix), JSON.stringify(data.mobile.matrix), data.method, data.sources.join("; "), data.retrieved_at])]
    .map(row => row.map(quote).join(",")).join("\r\n");
}
