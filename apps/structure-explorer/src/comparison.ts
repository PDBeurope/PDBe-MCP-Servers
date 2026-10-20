import type { Structure } from "molstar/lib/mol-model/structure/structure";
import type { ElementIndex } from "molstar/lib/mol-model/structure/model/indexing.js";
import { Mat4 } from "molstar/lib/mol-math/linear-algebra/3d/mat4.js";
import { Vec3 } from "molstar/lib/mol-math/linear-algebra/3d/vec3.js";
import { arrayRms } from "molstar/lib/mol-util/array.js";
import { Color } from "molstar/lib/mol-util/color/color.js";
import { ColorScale } from "molstar/lib/mol-util/color/scale.js";

export const metricSources = {
  alignment: "PDBe precomputed superposition matrices",
  ca_selection: "Mol* residue.traceElementIndex (occupied Cα only)",
  coordinates: "Mol* unit.conformation.position (displayed, transformed structure)",
  displacement: "Mol* Vec3.distance",
  rmsd: "Mol* arrayRms over the per-pair Cα distances; no refitting",
  coverage: "Observed and SIFTS-mapped pair counts only; no derived percentages",
} as const;

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
export interface AlphaCarbon {
  position: Vec3; altloc: string; occupancy: number; comp_id: string;
}
export interface Measurement extends ComparisonPair {
  displacement: number | null; reference_altloc: string | null; mobile_altloc: string | null;
  reference_comp_id: string | null; mobile_comp_id: string | null;
}

/** Source matrices use rows; MolViewSpec expects flattened column-major matrices. */
export function mvsMatrix(matrix: number[][]): number[] {
  return Mat4.ofRows(matrix);
}

/** Read Mol*'s trace Cα and its displayed position, including the PDBe transform.
 * Mol* owns trace-atom selection and coordinate transformation. We only filter
 * for the requested label chain, occupied Cα atoms and finite coordinates.
 */
export function alphaCarbons(structure: Structure, chain: string): Map<number, AlphaCarbon> {
  const result = new Map<number, AlphaCarbon>();
  for (const unit of structure.units) {
    if (unit.kind !== 0) continue; // Mol* Unit.Kind.Atomic
    const { atomicHierarchy: h, atomicConformation: c } = unit.model;
    if (!c.xyzDefined) continue;
    for (let offset = 0; offset < unit.elements.length; offset++) {
      const i: ElementIndex = unit.elements[offset];
      const ri = h.residueAtomSegments.index[i];
      if (h.derived.residue.traceElementIndex[ri] !== i) continue;
      if (h.atoms.label_atom_id.value(i) !== "CA" || h.atoms.type_symbol.value(i) !== "C") continue;
      if (h.chains.label_asym_id.value(h.chainAtomSegments.index[i]) !== chain) continue;
      const label = h.residues.label_seq_id.value(ri);
      const occupancy = c.occupancy.value(i);
      const position = unit.conformation.position(i, Vec3());
      if (!Vec3.isFinite(position) || !Number.isFinite(occupancy) || occupancy <= 0) continue;
      const altloc = h.atoms.label_alt_id.value(i) || "";
      result.set(label, { position, occupancy, altloc, comp_id: h.atoms.label_comp_id.value(i) });
    }
  }
  return result;
}

export function measurePairs(data: ComparisonData, reference: Map<number, AlphaCarbon>, mobile: Map<number, AlphaCarbon>) {
  const rows: Measurement[] = data.pairs.map(pair => {
    const a = reference.get(pair.reference.label_seq_id), b = mobile.get(pair.mobile.label_seq_id);
    const displacement = a && b ? Vec3.distance(a.position, b.position) : null;
    return { ...pair, displacement, reference_altloc: a?.altloc ?? null, mobile_altloc: b?.altloc ?? null,
      reference_comp_id: a?.comp_id ?? null, mobile_comp_id: b?.comp_id ?? null };
  });
  const distances = rows.flatMap(r => r.displacement === null ? [] : [r.displacement]);
  return { rows, measured_count: distances.length,
    rmsd: distances.length >= 3 ? arrayRms(distances) : null,
    metric_sources: metricSources };
}

const displacementScale = ColorScale.create({ domain: [0, 5], listOrName: [Color(0x2787b5), Color(0xdb4a39)] });
export function displacementColor(distance: number | null): string {
  if (distance === null) return "#b7b7b7";
  return Color.toHexStyle(displacementScale.color(distance));
}
export function comparisonCsv(data: ComparisonData, rows: Measurement[]): string {
  const quote = (v: unknown) => {
    const text = String(v ?? "");
    const safe = typeof v === "string" && /^\s*[=+@-]/.test(text) ? `'${text}` : text;
    return `"${safe.replaceAll('"', '""')}"`;
  };
  const columns = ["uniprot_accession", "uniprot_position", "segment_index", "reference_pdb", "reference_model_id", "reference_label_chain", "reference_auth_chain", "reference_label_residue", "reference_auth_residue", "reference_insertion_code", "reference_comp_id", "reference_altloc", "mobile_pdb", "mobile_model_id", "mobile_label_chain", "mobile_auth_chain", "mobile_label_residue", "mobile_auth_residue", "mobile_insertion_code", "mobile_comp_id", "mobile_altloc", "ca_displacement_angstrom", "reference_matrix_rows", "mobile_matrix_rows", "method", "metric_sources", "sources", "retrieved_at"];
  return [columns, ...rows.map(r => [data.uniprot_accession, r.uniprot_position, data.segment.index,
    data.reference.pdb_id, data.reference.model_id, data.reference.chain.label_asym_id, data.reference.chain.auth_asym_id,
    r.reference.label_seq_id, r.reference.auth_seq_id, r.reference.insertion_code, r.reference_comp_id ?? r.reference.comp_id, r.reference_altloc,
    data.mobile.pdb_id, data.mobile.model_id, data.mobile.chain.label_asym_id, data.mobile.chain.auth_asym_id,
    r.mobile.label_seq_id, r.mobile.auth_seq_id, r.mobile.insertion_code, r.mobile_comp_id ?? r.mobile.comp_id, r.mobile_altloc,
    r.displacement?.toFixed(6), JSON.stringify(data.reference.matrix), JSON.stringify(data.mobile.matrix), data.method, JSON.stringify(metricSources), data.sources.join("; "), data.retrieved_at])]
    .map(row => row.map(quote).join(",")).join("\r\n");
}
