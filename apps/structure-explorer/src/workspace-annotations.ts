import type { Annotation } from "./annotations";
import type { WorkspaceLayer, WorkspaceScene } from "./workspace";

export type OptionalData = "ligands" | "annotations";
export function layerCategory(layer: WorkspaceLayer): OptionalData | undefined {
  if (layer.category === "ligand" || /(?:^|-)ligand-\d+$/.test(layer.id)) return "ligands";
  if (layer.category === "source_annotation" || /(?:^|-)annotation-\d+$/.test(layer.id)) return "annotations";
  return undefined;
}
function isLigandSource(source: string): boolean {
  return /^ligands?(?:\b|[_-])/i.test(source.trim());
}
/** A Ligand-labelled residue track is not the deposited ligand molecule inventory. */
export function isLigandAnnotationLayer(scene: WorkspaceScene, layer: WorkspaceLayer): boolean {
  if (layerCategory(layer) !== "annotations") return false;
  const records = scene.structures.find(structure => structure.id === layer.structure_id)?.annotations ?? [];
  const ids = new Set([...(layer.source_annotation_ids ?? []), ...(layer.source_annotation_id ? [layer.source_annotation_id] : [])]);
  const matching = ids.size ? records.filter(record => ids.has(record.id))
    : records.filter((_record, index) => index + 1 === Number(layer.id.match(/annotation-(\d+)$/)?.[1]));
  if (matching.length) return matching.every(record => isLigandSource(record.source));
  return !ids.size && layer.name.split(" · ").some(isLigandSource);
}
export function ligandLayerLabel(scene: WorkspaceScene, layer: WorkspaceLayer): string {
  const structure = scene.structures.find(structure => structure.id === layer.structure_id);
  const selector = layer.component?.["selector"] as Record<string, unknown> | undefined;
  if (!structure || !selector || Array.isArray(selector)) return layer.name;
  const ligand = structure.ligands.find(ligand => ligand.label_asym_id === selector["label_asym_id"]
    && ligand.auth_seq_id === selector["auth_seq_id"] && ligand.comp_id === selector["label_comp_id"]
    && (ligand.insertion_code ?? "") === (selector["pdbx_PDB_ins_code"] ?? ""));
  return ligand ? `${structure.pdb_id.toUpperCase()} · ${ligand.comp_id} · label chain ${ligand.label_asym_id}${ligand.auth_asym_id ? ` / author ${ligand.auth_asym_id}` : ""} · residue ${ligand.auth_seq_id}${ligand.insertion_code ?? ""}` : layer.name;
}
function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, item) => item && typeof item === "object" && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
}
export function uniqueAnnotations(annotations: Annotation[]): Annotation[] {
  const seen = new Set<string>();
  return annotations.filter(annotation => {
    const { id: _id, ...record } = annotation;
    const key = canonical({ ...record, segments: [...record.segments].sort((a, b) => canonical(a).localeCompare(canonical(b))) });
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
}
export interface AnnotationGroup {
  structureId: string; pdbId: string; chainId: string; provider: string;
  features: Annotation[]; layerIds: string[]; covered: number; total: number; percent: number | null;
}
/** Coverage counts unique listed residue identities, never geometric neighbourhoods or scores. */
export function annotationGroups(scene: WorkspaceScene): AnnotationGroup[] {
  const groups: AnnotationGroup[] = [];
  for (const structure of scene.structures) {
    const records = (structure.annotations ?? []).filter(feature => !isLigandSource(feature.source));
    const chainIds = new Set(records.flatMap(feature => feature.segments.map(segment => segment.label_asym_id)));
    for (const chainId of chainIds) {
      const residues = new Set((structure.chains?.find(chain => chain.label_asym_id === chainId)?.residues ?? [])
        .map(residue => residue.label_seq_id).filter((id): id is number => Number.isInteger(id) && id! > 0));
      for (const provider of new Set(records.filter(feature => feature.segments.some(segment => segment.label_asym_id === chainId)).map(feature => feature.source))) {
        const matching = records.filter(feature => feature.source === provider && feature.segments.some(segment => segment.label_asym_id === chainId));
        const features = uniqueAnnotations(matching);
        const covered = new Set<number>();
        for (const feature of features) for (const segment of feature.segments) {
          if (segment.label_asym_id !== chainId) continue;
          for (const id of residues) if (segment.start <= id && id <= segment.end) covered.add(id);
        }
        const ids = new Set(matching.map(feature => feature.id));
        const layerIds = scene.layers.filter(layer => layer.structure_id === structure.id && layerCategory(layer) === "annotations"
          && (!Array.isArray(layer.component?.["selector"]) || layer.component["selector"].some(selector => selector.label_asym_id === chainId))
          && (layer.source_annotation_ids?.length ? layer.source_annotation_ids.some(id => ids.has(id))
            : layer.source_annotation_id ? ids.has(layer.source_annotation_id) : matching.some(feature => (structure.annotations ?? []).indexOf(feature) + 1 === Number(layer.id.match(/annotation-(\d+)$/)?.[1])))).map(layer => layer.id);
        groups.push({ structureId: structure.id, pdbId: structure.pdb_id, chainId, provider, features, layerIds,
          covered: covered.size, total: residues.size, percent: residues.size ? 100 * covered.size / residues.size : null });
      }
    }
  }
  const priority = (group: AnnotationGroup): number => {
    const name = group.provider.trim();
    if (/^uniprot(?:kb)?(?:\b|[_-])/i.test(name)) return 0;
    return 1;
  };
  // Stable sorting keeps the original relative order within each category.
  return groups.sort((a, b) => priority(a) - priority(b));
}
export interface FetchedStructure { structureId: string; scene: WorkspaceScene }
/** Enrich metadata via a complete scene upsert: keep coordinates, transforms and correspondence intact. */
export function mergeOptionalScene(base: WorkspaceScene, fetched: FetchedStructure[], kind: OptionalData, visible: boolean): WorkspaceScene {
  const scene = structuredClone(base);
  for (const result of fetched) {
    const target = scene.structures.find(structure => structure.id === result.structureId);
    const supplied = result.scene.structures[0];
    if (!target || !supplied || target.pdb_id !== supplied.pdb_id) throw new Error("Optional data does not match the intended structure");
    const allowedChains = new Set(target.chains?.map(chain => chain.label_asym_id));
    if (kind === "ligands") target.ligands = structuredClone(supplied.ligands);
    else target.annotations = uniqueAnnotations((supplied.annotations ?? []).map(feature => ({ ...feature,
      segments: feature.segments.filter(segment => !scene.comparison || allowedChains.has(segment.label_asym_id)),
    })).filter(feature => feature.segments.length));
    target.data_status = { ...target.data_status, [kind]: supplied.data_status?.[kind] ?? "loaded" };
    // Structure metadata carries the evidence URLs used by the optional lookup.
    target.data_sources = [...new Set([...(target.data_sources ?? []), ...(supplied.data_sources ?? [])])];
    const annotationIds = new Set(target.annotations?.map(feature => feature.id));
    for (const incoming of result.scene.layers.filter(layer => layerCategory(layer) === kind)) {
      if (kind === "annotations" && incoming.source_annotation_ids?.length && !incoming.source_annotation_ids.some(id => annotationIds.has(id))) continue;
      if (kind === "annotations" && incoming.source_annotation_id && !annotationIds.has(incoming.source_annotation_id)) continue;
      const layer = structuredClone(incoming);
      if (kind === "annotations" && scene.comparison && layer.component) {
        const selectors = layer.component["selector"];
        if (Array.isArray(selectors)) {
          const selected = selectors.filter(selector => allowedChains.has(selector.label_asym_id));
          // A feature ID may be shared across chains. Its presence in metadata
          // does not mean every visual layer for that feature belongs here.
          if (!selected.length) continue;
          layer.component["selector"] = selected;
        }
      }
      let id = `${target.id}-${incoming.id}`;
      const existing = scene.layers.find(layer => layer.id === id);
      if (existing && layerCategory(existing) === kind) continue; // preserve existing edits
      let suffix = 1;
      while (scene.layers.some(layer => layer.id === id)) id = `${target.id}-${incoming.id}-${suffix++}`;
      scene.layers.push({ ...layer, id, structure_id: target.id, name: `${target.pdb_id.toUpperCase()} · ${layer.name}`, visible });
    }
  }
  for (const layer of scene.layers) if (layerCategory(layer) === kind) {
    layer.visible = visible && !(kind === "annotations" && isLigandAnnotationLayer(scene, layer));
  }
  return scene;
}
