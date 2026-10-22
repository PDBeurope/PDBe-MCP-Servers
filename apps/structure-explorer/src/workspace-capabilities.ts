/** Coordinate metadata and camera navigation; no scientific measurements or inferred sites. */
import type { ElementIndex } from "molstar-mvs/lib/mol-model/structure/model/indexing.js";
import type { Structure } from "molstar-mvs/lib/mol-model/structure/structure.js";
import { Vec3 } from "molstar-mvs/lib/mol-math/linear-algebra/3d/vec3.js";
import type { LigandInstance } from "./workspace";
import type { ComparisonResidue } from "./comparison";

export interface SceneNode { kind: string; ref?: string; params?: Record<string, unknown>; children?: SceneNode[] }

export function residuePositions(structure: Structure, chain?: string, label?: number): Vec3[] {
  const points: Vec3[] = [];
  for (const unit of structure.units) {
    if (unit.kind !== 0) continue;
    const h = unit.model.atomicHierarchy;
    for (let offset = 0; offset < unit.elements.length; offset++) {
      const i: ElementIndex = unit.elements[offset];
      if (chain !== undefined && h.chains.label_asym_id.value(h.chainAtomSegments.index[i]) !== chain) continue;
      if (label !== undefined && h.residues.label_seq_id.value(h.residueAtomSegments.index[i]) !== label) continue;
      const point = unit.conformation.position(i, Vec3());
      if (Vec3.isFinite(point)) points.push(point);
    }
  }
  return points;
}
export function attachLayerRefs(root: SceneNode, layers: import("./workspace").WorkspaceLayer[]) {
  function visit(node: SceneNode) {
    if (node.kind === "structure") {
      const visible = layers.filter(layer => layer.structure_id === node.ref && layer.visible && layer.kind === "component");
      const components = node.children?.filter(child => child.kind.startsWith("component")) ?? [];
      visible.forEach((layer, index) => { if (components[index]) components[index].ref = layer.id; });
    }
    node.children?.forEach(visit);
  }
  visit(root);
}

/** Fill the same pickers for Builder scenes, which do not fetch Explorer metadata. */
export function coordinateInventory(structure: Structure) {
  const ligands = new Map<string, LigandInstance>();
  const chains = new Map<string, { label_asym_id: string; auth_asym_id: string; entity_id: string; residues: ComparisonResidue[] }>();
  const seen = new Set<string>();
  for (const unit of structure.units) {
    if (unit.kind !== 0) continue;
    const h = unit.model.atomicHierarchy;
    for (let offset = 0; offset < unit.elements.length; offset++) {
      const i: ElementIndex = unit.elements[offset], ri = h.residueAtomSegments.index[i];
      const key = `${unit.model.id}/${ri}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const ci = h.chainAtomSegments.index[i];
      const type = unit.model.entities.data.type.value(h.index.getEntityFromChain(ci));
      const labelChain = h.chains.label_asym_id.value(ci), authChain = h.chains.auth_asym_id.value(ci);
      const residue = { label_seq_id: h.residues.label_seq_id.value(ri), auth_seq_id: h.residues.auth_seq_id.value(ri),
        insertion_code: h.residues.pdbx_PDB_ins_code.value(ri) || "", comp_id: h.atoms.label_comp_id.value(i) };
      if (type === "non-polymer" || type === "branched") {
        const ligand = { label_asym_id: labelChain, auth_asym_id: authChain, auth_seq_id: residue.auth_seq_id,
          insertion_code: residue.insertion_code, comp_id: residue.comp_id };
        ligands.set(JSON.stringify(ligand), ligand);
      } else if (type === "polymer" && residue.label_seq_id > 0) {
        const chain = chains.get(labelChain) ?? { label_asym_id: labelChain, auth_asym_id: authChain,
          entity_id: h.chains.label_entity_id.value(ci), residues: [] };
        chain.residues.push(residue); chains.set(labelChain, chain);
      }
    }
  }
  return { ligands: [...ligands.values()], chains: [...chains.values()] };
}
