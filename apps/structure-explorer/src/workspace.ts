/** The transport and saved-artifact contract. Scientific definitions are validated by Python. */
export interface LigandInstance {
  label_asym_id: string; auth_asym_id: string; auth_seq_id: number; insertion_code: string; comp_id: string;
}
export interface WorkspaceStructure {
  id: string; pdb_id: string; options: Record<string, unknown>; ligands: LigandInstance[];
  chains?: { label_asym_id: string; auth_asym_id: string; entity_id: string; residues?: import("./comparison").ComparisonResidue[] }[];
  annotations?: import("./annotations").Annotation[];
  data_sources?: string[];
  data_status?: Partial<Record<"annotations" | "ligands", "not_requested" | "loaded" | "unavailable">>;
}
export interface WorkspaceLayer {
  id: string; structure_id: string; name: string; kind: "component" | "annotation";
  visible: boolean; component?: Record<string, unknown>; annotation?: Record<string, unknown>;
  sources: string[];
  category?: "ligand" | "source_annotation";
  source_annotation_id?: string;
  source_annotation_ids?: string[];
}
export interface WorkspaceScene {
  id: string; title: string; structures: WorkspaceStructure[]; layers: WorkspaceLayer[];
  comparison?: import("./comparison").ComparisonData & { reference_id: string; mobile_id: string };
}
export interface Workspace {
  version: 1; id: string; revision: number; view?: { active_scene_id?: string; cameras: Record<string, { position: number[]; target: number[]; up: number[] }> }; title: string; scenes: WorkspaceScene[]; sources: string[]; warnings: string[];
}
export type WorkspaceOperation = {
  op: "upsert_structure" | "remove_structure" | "upsert_layer" | "remove_layer" | "set_visibility" | "upsert_scene" | "remove_scene";
  scene_id: string; target_id: string; layer?: WorkspaceLayer; structure?: WorkspaceStructure; scene?: WorkspaceScene; visible?: boolean;
};
export function validateEnvelope(value: unknown): Workspace {
  const w = value as Workspace;
  if (!w || w.version !== 1 || typeof w.id !== "string" || !Number.isInteger(w.revision) || w.revision < 0
      || !Array.isArray(w.scenes) || !w.scenes.length || w.scenes.length > 20) throw new Error("Unsupported workspace envelope");
  const sceneIds = new Set<string>();
  for (const scene of w.scenes) {
    if (sceneIds.has(scene.id) || !Array.isArray(scene.structures) || !Array.isArray(scene.layers)) throw new Error("Invalid workspace scene");
    sceneIds.add(scene.id);
    const structures = new Set(scene.structures.map(s => s.id));
    if (structures.size !== scene.structures.length || new Set(scene.layers.map(l => l.id)).size !== scene.layers.length
        || scene.layers.some(l => !structures.has(l.structure_id) || !["component", "annotation"].includes(l.kind))) throw new Error("Invalid workspace references");
  }
  return w;
}
export function checkRevision(current: Workspace | undefined, next: Workspace): void {
  if (current?.id !== next.id) return;
  if (next.revision < current.revision) throw new Error("Stale workspace result ignored; use the latest revision");
  const scientificState = (w: Workspace) => JSON.stringify({ title: w.title, scenes: w.scenes, sources: w.sources, warnings: w.warnings });
  if (next.revision === current.revision && scientificState(next) !== scientificState(current)) throw new Error("Conflicting workspace state at the same revision; use the latest workspace");
}
