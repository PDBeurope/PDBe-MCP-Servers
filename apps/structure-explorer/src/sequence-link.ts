import type { Structure } from "molstar-mvs/lib/mol-model/structure/structure.js";
import type { Annotation } from "./annotations";

export interface SequenceResidue {
  position: number;
  label_seq_id: number;
  letter: string;
  comp_id: string;
  auth_seq_id: number | null;
  insertion_code: string;
  has_coordinates: boolean;
  model_ids: number[];
  operator_ids: string[];
}

export interface LinkedSequence {
  sequence: string;
  residues: SequenceResidue[];
  label_asym_id: string;
  auth_asym_id: string;
  entity_id: string;
}

/** Build the entity sequence axis and map it to observed chain residues by label_seq_id. */
export function linkedSequence(structure: Structure, labelAsymId: string): LinkedSequence | undefined {
  for (const unit of structure.units) {
    if (unit.kind !== 0) continue;
    const model = unit.model;
    const hierarchy = model.atomicHierarchy;
    let entityKey: number | undefined;
    let authAsymId = "";
    let entityId = "";
    for (let offset = 0; offset < unit.elements.length; offset++) {
      const atom = unit.elements[offset];
      const chainIndex = hierarchy.chainAtomSegments.index[atom];
      if (hierarchy.chains.label_asym_id.value(chainIndex) !== labelAsymId) continue;
      entityKey = hierarchy.index.getEntityFromChain(chainIndex);
      authAsymId = hierarchy.chains.auth_asym_id.value(chainIndex);
      entityId = model.entities.data.id.value(entityKey);
      break;
    }
    if (entityKey === undefined) continue;
    const entitySequence = model.sequence.byEntityKey[entityKey]?.sequence;
    if (!entitySequence || entitySequence.kind !== "protein") return undefined;

    const observed = new Map<number, Omit<SequenceResidue, "position" | "label_seq_id" | "letter">>();
    for (const candidate of structure.units) {
      if (candidate.kind !== 0 || candidate.model !== model) continue;
      const candidateHierarchy = candidate.model.atomicHierarchy;
      for (let offset = 0; offset < candidate.elements.length; offset++) {
        const atom = candidate.elements[offset];
        const chain = candidateHierarchy.chainAtomSegments.index[atom];
        if (candidateHierarchy.chains.label_asym_id.value(chain) !== labelAsymId) continue;
        const residue = candidateHierarchy.residueAtomSegments.index[atom];
        const position = candidateHierarchy.residues.label_seq_id.value(residue);
        if (position < 1) continue;
        const current = observed.get(position) ?? {
          comp_id: candidateHierarchy.atoms.label_comp_id.value(atom),
          auth_seq_id: candidateHierarchy.residues.auth_seq_id.value(residue),
          insertion_code: candidateHierarchy.residues.pdbx_PDB_ins_code.value(residue) || "",
          has_coordinates: true, model_ids: [], operator_ids: [],
        };
        if (!current.model_ids.includes(candidate.model.modelNum)) current.model_ids.push(candidate.model.modelNum);
        if (!current.operator_ids.includes(candidate.conformation.operator.instanceId)) current.operator_ids.push(candidate.conformation.operator.instanceId);
        observed.set(position, current);
      }
    }

    const sequenceByPosition = new Map<number, { letter: string; comp_id: string }>();
    for (let i = 0; i < entitySequence.length; i++) {
      const position = entitySequence.seqId.value(i);
      if (position > 0) sequenceByPosition.set(position, {
        letter: entitySequence.code.value(i) || "X",
        comp_id: entitySequence.compId.value(i) || observed.get(position)?.comp_id || "UNK",
      });
    }
    const maxPosition = Math.max(0, ...sequenceByPosition.keys());
    if (!maxPosition) return undefined;
    const residues: SequenceResidue[] = [];
    const sequence = Array.from({ length: maxPosition }, (_, index) => {
      const position = index + 1;
      const entityResidue = sequenceByPosition.get(position);
      const coordinateResidue = observed.get(position);
      const letter = entityResidue?.letter ?? "X";
      residues.push({
        position, label_seq_id: position, letter,
        comp_id: coordinateResidue?.comp_id ?? entityResidue?.comp_id ?? "UNK",
        auth_seq_id: coordinateResidue?.auth_seq_id ?? null,
        insertion_code: coordinateResidue?.insertion_code ?? "",
        has_coordinates: !!coordinateResidue,
        model_ids: coordinateResidue?.model_ids ?? [],
        operator_ids: coordinateResidue?.operator_ids ?? [],
      });
      return letter;
    }).join("");
    return { sequence, residues, label_asym_id: labelAsymId, auth_asym_id: authAsymId, entity_id: entityId };
  }
  return undefined;
}

export interface NightingaleFeature {
  accession: string;
  type?: string;
  color?: string;
  shape?: string;
  tooltipContent?: string;
  locations: { fragments: { start: number; end: number }[] }[];
}

export interface AnnotationTrackGroup {
  id: string;
  label: string;
  features: NightingaleFeature[];
}

export function observedTrack(sequence: LinkedSequence): NightingaleFeature[] {
  const positions = sequence.residues.filter(residue => residue.has_coordinates).map(residue => residue.position);
  const fragments: { start: number; end: number }[] = [];
  for (const position of positions) {
    const previous = fragments.at(-1);
    if (previous && previous.end + 1 === position) previous.end = position;
    else fragments.push({ start: position, end: position });
  }
  return fragments.length ? [{ accession: "observed-residues", color: "#16856a", shape: "rectangle",
    tooltipContent: "Residues with coordinates in the selected chain", locations: [{ fragments }] }] : [];
}

function annotationFeature(feature: Annotation, chain: string, length: number, color: string, type: string): NightingaleFeature | undefined {
  const fragments = feature.segments.filter(segment => segment.label_asym_id === chain)
    .map(segment => ({ start: Math.max(1, segment.start), end: Math.min(length, segment.end) }))
    .filter(segment => segment.end >= segment.start);
  if (!fragments.length) return undefined;
  const details = [feature.source, feature.accession, feature.name, feature.description].filter(Boolean).join(" · ");
  return { accession: feature.id, type, color, tooltipContent: details, locations: [{ fragments }] };
}

/** Group source records into tracks at runtime; the UI does not hard-code annotation types. */
export function annotationTrackGroups(annotations: Annotation[], chain: string, length: number): AnnotationTrackGroup[] {
  const groups = new Map<string, AnnotationTrackGroup>();
  const colors = ["#d47532", "#6a76b8", "#16856a", "#c76b78", "#527fc1", "#9473bc", "#609c5d"];
  for (const feature of annotations) {
    const provider = feature.source?.trim() || "Annotations";
    const type = feature.kind?.trim() || "features";
    const id = `${encodeURIComponent(provider.toLowerCase())}:${encodeURIComponent(type.toLowerCase())}`;
    let group = groups.get(id);
    if (!group) {
      group = { id, label: `${provider} · ${type.replaceAll("_", " ")}`, features: [] };
      groups.set(id, group);
    }
    const text = `${feature.kind} ${feature.name} ${feature.description}`.toLowerCase();
    const shape = /strand/.test(text) ? "strand" : /helix/.test(text) ? "helix"
      : /site/.test(text) ? "diamond" : /domain/.test(text) ? "roundRectangle" : "rectangle";
    const item = annotationFeature(feature, chain, length, colors[(groups.size - 1) % colors.length], type);
    if (item) group.features.push({ ...item, shape });
  }
  return [...groups.values()].filter(group => group.features.length > 0)
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function annotationPositions(features: Annotation[], chain: string, length: number): number[] {
  return [...new Set(features.flatMap(feature => feature.segments
    .filter(segment => segment.label_asym_id === chain)
    .flatMap(segment => Array.from({ length: Math.max(0, Math.min(length, segment.end) - Math.max(1, segment.start) + 1) }, (_, i) => Math.max(1, segment.start) + i))))].sort((a, b) => a - b);
}
