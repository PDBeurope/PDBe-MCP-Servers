import { App, applyDocumentTheme, applyHostStyleVariables, type McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import type { Viewer } from "molstar-mvs/lib/apps/viewer/app.js";
import { createWorkspaceViewer, displayedStructure } from "./workspace-renderer";
import { residuePositions, attachLayerRefs, coordinateInventory, type SceneNode } from "./workspace-capabilities";
import { validateEnvelope, checkRevision, type Workspace, type WorkspaceOperation } from "./workspace";
import { annotationsAt } from "./annotations";
import { isLigandAnnotationLayer, ligandLayerLabel, layerCategory, mergeOptionalAnnotations, mergeOptionalScene, type FetchedAnnotations, type FetchedStructure, type OptionalData } from "./workspace-annotations";
import { comparisonCsv } from "./comparison";
import { linkedSequence, observedTrack, annotationTrackGroups, type LinkedSequence, type SequenceResidue, type NightingaleFeature } from "./sequence-link";
import NightingaleManager from "@nightingale-elements/nightingale-manager";
import NightingaleSequence from "@nightingale-elements/nightingale-sequence";
import NightingaleTrack from "@nightingale-elements/nightingale-track";
import NightingaleNavigation from "@nightingale-elements/nightingale-navigation";
import { StructureElement, StructureProperties } from "molstar-mvs/lib/mol-model/structure.js";
import { OrderedSet } from "molstar-mvs/lib/mol-data/int.js";
import type { UnitIndex } from "molstar-mvs/lib/mol-model/structure/structure/element/util.js";
import type { Structure } from "molstar-mvs/lib/mol-model/structure/structure.js";
import "./mvs.css";
import "./workspace.css";

// Keep these constructors live through bundling: Nightingale packages declare
// sideEffects:false, but their custom-element registration happens at import time.
const nightingaleElements: [string, CustomElementConstructor][] = [
  ["nightingale-manager", NightingaleManager],
  ["nightingale-sequence", NightingaleSequence],
  ["nightingale-track", NightingaleTrack],
  ["nightingale-navigation", NightingaleNavigation],
];
for (const [name, element] of nightingaleElements) {
  if (!customElements.get(name)) customElements.define(name, element);
}

interface LegendItem {
  label: string;
  representation: string;
  colors?: string[];
}

interface SceneResult {
  version: 1;
  workspace?: Workspace;
  builder?: { pdb_id: string; title: string; description?: string };
  story?: { title: string; description?: string };
  scenes?: { id: string; title: string; description?: string; builder: { pdb_id: string }; legend: LegendItem[]; coordinate_url: string }[];
  mvsj: Record<string, unknown>;
  legend?: LegendItem[];
  warnings: string[];
  coordinate_url?: string;
}
interface ToolResult {
  isError?: boolean;
  content?: { type: string; text?: string }[];
  _meta?: Record<string, unknown>;
}
interface ContactRecord { ligand_atoms?: string[]; interaction_type?: string; interaction_details?: string[] | string; distance?: number | string; end?: { chain_id?: string; label_asym_id?: string; author_residue_number?: string | number; author_insertion_code?: string; chem_comp_id?: string; atom_names?: string[] }; [key: string]: unknown }
interface LigandData { pdb_id: string; ligands: Record<string, unknown>[]; selected?: Record<string, unknown> | null; contacts: ContactRecord[]; interaction_source?: string | null; retrieved_at: string; validation?: unknown; validation_source?: string; entry_sources?: string[]; warnings?: string[]; assemblies?: unknown[]; assembly_context?: unknown; assembly_source?: string; chains?: Record<string, unknown>[]; molecules?: Record<string, unknown>[]; annotations?: Record<string, unknown>[]; contact_lines_enabled?: boolean; contact_lines_unavailable_reason?: string }

function el<T extends HTMLElement = HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}
function status(message: string, error = false): void {
  el("status").textContent = message;
  el("status").classList.toggle("error", error);
}
function theme(context: McpUiHostContext): void {
  if (context.theme) applyDocumentTheme(context.theme);
  if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
}

const app = new App({ name: "PDBe Molecular Workspace", version: "0.1.0" });
let viewer: Viewer | undefined;
let scene: SceneResult | undefined;
let connected = false;
let disposed = false;
let revision = 0;
let work = Promise.resolve();
let downloadUrl: string | undefined;
let navigating = false;
let workspace: Workspace | undefined;
let renderedMvs: Record<string, unknown> | undefined;
let updating = false;
let selectionContext: Record<string, unknown> | undefined;
let loadState = "pending";
let inventories = new Map<string, ReturnType<typeof coordinateInventory>>();
let ligandData: LigandData | undefined;
let contactObjectUrl: string | undefined;
let ligandWorkspaceSnapshot: Workspace | undefined;
let sequenceMap: LinkedSequence | undefined;
let sequenceStructureId: string | undefined;
let sequenceCoordinates: Structure | undefined;
let sequencePdbId: string | undefined;
let sequenceAnnotations: import("./annotations").Annotation[] = [];
let sequenceCommittedPositions: number[] = [];
let sequenceTrackFeaturePositions = new Map<string, number[]>();
let sequenceTrackFeatureAnnotations = new Map<string, import("./annotations").Annotation>();
let sequenceTooltipTarget: HTMLElement | undefined;
let sequenceTooltipPinned = false;
let sequenceVisible = true;
let sequenceTargetsByValue = new Map<string, { structureId: string; pdbId: string; structure: Structure; chainId: string; authChainId: string; sequence: LinkedSequence }>();
let sequenceTrackCatalog: { id: string; label: string; feature_count: number }[] = [];
let sequenceTrackSelection: Set<string> | undefined;

function activeWorkspaceScene() {
  const key = viewer?.plugin.managers.snapshot.current?.key;
  return workspace?.scenes.find(s => s.id === key) ?? workspace?.scenes[0];
}
function workspaceControls() {
  const disabled = !connected || !workspace || !viewer || updating || disposed || !["loaded", "empty"].includes(loadState);
  for (const id of ["save-workspace", "export-comparison"]) el<HTMLButtonElement>(id).disabled = disabled;
  for (const input of el("workspace-panel").querySelectorAll<HTMLInputElement>("input[type=checkbox]")) input.disabled = disabled;
  el("workspace-panel").hidden = !workspace || !!scene?.story;
  el("comparison-panel").hidden = !activeWorkspaceScene()?.comparison;
  el<HTMLButtonElement>("export-comparison").disabled = disabled || !activeWorkspaceScene()?.comparison;
  el<HTMLButtonElement>("ask-selection").disabled = !selectionContext || !app.getHostCapabilities()?.message;
}
function renderWorkspaceControls() {
  const active = activeWorkspaceScene();
  el("workspace-id").textContent = workspace ? `${workspace.id} · revision ${workspace.revision}` : "";
  el("layers").replaceChildren();
  el("ligand-layers").replaceChildren();
  if (!active) { workspaceControls(); return; }
  const options = el("comparison-options"); options.hidden = !active.comparison;
  for (const [kind, id] of [["ligands", "show-ligands"]] as const) {
    const input = el<HTMLInputElement>(id), layers = active.layers.filter(layer => layerCategory(layer) === kind && !isLigandAnnotationLayer(active, layer));
    input.checked = layers.some(layer => layer.visible);
    input.indeterminate = input.checked && layers.some(layer => !layer.visible);
  }
  el("optional-data-status").textContent = active.structures.map(structure => {
    const labels = (["ligands", "annotations"] as const).map(kind => `${kind}: ${structure.data_status?.[kind] ?? (structure[kind]?.length ? "loaded" : "not requested")}`);
    return `${structure.pdb_id.toUpperCase()} · ${labels.join("; ")}`;
  }).join(" · ");
  const ligandLayers = active.layers.filter(layer => layerCategory(layer) === "ligands");
  const ligandDataLoaded = active.structures.every(structure => structure.data_status?.ligands === "loaded");
  el("ligand-status").textContent = ligandLayers.length
    ? "Deposited molecules. Label and author chain identifiers may differ."
    : ligandDataLoaded ? "No deposited ligand molecules are available in this workspace."
    : "Enable Show ligands to load deposited molecules into this workspace.";
  for (const layer of active.layers) {
    // Source tracks have one annotation summary rather than hundreds of repeated layer rows.
    if (layerCategory(layer) === "annotations") continue;
    const label = document.createElement("label"), checkbox = document.createElement("input");
    checkbox.type = "checkbox"; checkbox.checked = layer.visible; checkbox.dataset.layerId = layer.id;
    checkbox.addEventListener("change", () => { void mutate([{ op: "set_visibility", scene_id: active.id, target_id: layer.id, visible: checkbox.checked }]); });
    const focus = document.createElement("button"); focus.type = "button"; focus.textContent = "Focus";
    focus.disabled = !layer.visible;
    focus.addEventListener("click", () => {
      if (!viewer) return;
      const structure = displayedStructure(viewer, layer.id);
      const points = structure ? residuePositions(structure) : [];
      if (points.length) viewer.plugin.managers.camera.focusSpheres(points, center => ({ center, radius: 2 }), { minRadius: 8 });
    });
    const ligand = layerCategory(layer) === "ligands";
    label.append(checkbox, document.createTextNode(ligand ? ligandLayerLabel(active, layer) : `${layer.name} · ${layer.kind.replaceAll("_", " ")}`), focus);
    el(ligand ? "ligand-layers" : "layers").append(label);
  }
  workspaceControls();
}

function availableLigands(structure?: import("./workspace").WorkspaceStructure) {
  return structure?.ligands.length ? structure.ligands : inventories.get(`${activeWorkspaceScene()?.id}/${structure?.id}`)?.ligands ?? [];
}
function availableChains(structure?: import("./workspace").WorkspaceStructure) {
  return structure?.chains?.some(chain => chain.residues?.length) ? structure.chains : inventories.get(`${activeWorkspaceScene()?.id}/${structure?.id}`)?.chains ?? [];
}

function sequenceTargets() {
  const targets: { value: string; structureId: string; pdbId: string; structure: Structure; chainId: string; authChainId: string; sequence: LinkedSequence }[] = [];
  const active = activeWorkspaceScene();
  if (active && viewer) {
    for (const definition of active.structures) {
      const structure = displayedStructure(viewer, definition.id);
      if (!structure) continue;
      for (const chain of availableChains(definition)) {
        const sequence = linkedSequence(structure, chain.label_asym_id);
        if (sequence) targets.push({ value: JSON.stringify([definition.id, chain.label_asym_id]), structureId: definition.id,
          pdbId: definition.pdb_id, structure, chainId: chain.label_asym_id, authChainId: chain.auth_asym_id, sequence });
      }
    }
  } else if (viewer) {
    for (const ref of viewer.plugin.managers.structure.hierarchy.current.structures) {
      const structure = ref.cell.obj?.data;
      if (!structure) continue;
      const inventory = coordinateInventory(structure);
      for (const chain of inventory.chains) {
        const sequence = linkedSequence(structure, chain.label_asym_id);
        if (sequence) targets.push({ value: JSON.stringify([ref.cell.transform.ref, chain.label_asym_id]),
          structureId: ref.cell.transform.ref, pdbId: currentScene()?.builder.pdb_id ?? scene?.builder?.pdb_id ?? "", structure,
          chainId: chain.label_asym_id, authChainId: chain.auth_asym_id, sequence });
      }
    }
  }
  return targets;
}

function setSequenceHighlight(positions: number[]) {
  const ranges: string[] = [];
  for (const position of [...new Set(positions)].sort((a, b) => a - b)) {
    const previous = ranges.at(-1)?.split(":").map(Number);
    if (previous && previous[1] + 1 === position) ranges[ranges.length - 1] = `${previous[0]}:${position}`;
    else ranges.push(`${position}:${position}`);
  }
  const manager = el<HTMLElement>("sequence-manager");
  if (ranges.length) manager.setAttribute("highlight", ranges.join(","));
  else manager.removeAttribute("highlight");
}

function sequenceLoci(positions: number[]) {
  if (!sequenceCoordinates || !sequenceMap || !positions.length) return undefined;
  const selected = new Set(positions);
  const elements: { unit: (typeof sequenceCoordinates.units)[number]; indices: UnitIndex[] }[] = [];
  for (const unit of sequenceCoordinates.units) {
    if (unit.kind !== 0) continue;
    const h = unit.model.atomicHierarchy, indices: UnitIndex[] = [];
    for (let offset = 0; offset < unit.elements.length; offset++) {
      const atom = unit.elements[offset], residue = h.residueAtomSegments.index[atom], chain = h.chainAtomSegments.index[atom];
      if (h.chains.label_asym_id.value(chain) === sequenceMap.label_asym_id
        && selected.has(h.residues.label_seq_id.value(residue))) indices.push(offset as UnitIndex);
    }
    if (indices.length) elements.push({ unit, indices });
  }
  return elements.length ? StructureElement.Loci(sequenceCoordinates, elements.map(item => ({
    unit: item.unit, indices: OrderedSet.ofSortedArray(item.indices),
  }))) : undefined;
}

function showSequenceTooltip(positions: number[], annotation?: import("./annotations").Annotation, target?: HTMLElement, pinned = false) {
  const tooltip = el("sequence-tooltip");
  if (positions.length && sequenceTooltipPinned && !pinned) return;
  sequenceTooltipTarget?.removeAttribute("aria-describedby");
  sequenceTooltipTarget = target;
  sequenceTooltipPinned = pinned && positions.length > 0;
  if (sequenceTooltipTarget) sequenceTooltipTarget.setAttribute("aria-describedby", "sequence-tooltip");
  const tooltipContent = el("sequence-tooltip-content");
  if (!sequenceMap || !positions.length) { tooltip.hidden = true; tooltipContent.textContent = ""; return; }
  const matched = positions.map(position => sequenceMap!.residues.find(residue => residue.position === position)).filter((residue): residue is SequenceResidue => !!residue);
  const range = positions.length === 1 ? `Residue ${positions[0]}` : `Residues ${Math.min(...positions)}–${Math.max(...positions)} (${positions.length} mapped positions)`;
  const labels = matched.slice(0, 8).map(residue => `${residue.letter} ${residue.comp_id} · author ${residue.auth_seq_id}${residue.insertion_code} · ${residue.has_coordinates ? "coordinates present" : "no coordinates"}`);
  const annotations = annotation ? [annotation] : [...new Set(sequenceAnnotations.filter(item => item.segments.some(segment => segment.label_asym_id === sequenceMap!.label_asym_id
    && positions.some(position => segment.start <= position && position <= segment.end))))];
  const annotationText = annotations.map(item => `${item.source} · ${item.name}${item.accession ? ` (${item.accession})` : ""}${item.description ? `: ${item.description}` : ""}`).join("; ");
  tooltipContent.textContent = [annotationText || "Sequence selection", range, labels.join("; "), matched.length > 8 ? `…and ${matched.length - 8} more` : ""]
    .filter(Boolean).join(" — ");
  tooltip.hidden = false;
  if (target) {
    const bounds = target.getBoundingClientRect();
    const width = Math.min(440, window.innerWidth - 24);
    const left = Math.max(12, Math.min(bounds.left, window.innerWidth - width - 12));
    const height = tooltip.getBoundingClientRect().height;
    const top = bounds.bottom + 8 + height < window.innerHeight ? bounds.bottom + 8 : Math.max(12, bounds.top - height - 8);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  } else {
    tooltip.style.left = "12px";
    tooltip.style.top = "auto";
  }
}

function selectSequencePositions(positions: number[], source: string, annotation?: import("./annotations").Annotation, tooltipTarget?: HTMLElement, contextExtras?: Record<string, unknown>) {
  if (!sequenceMap || !sequenceStructureId || !sequenceCoordinates) return;
  const valid = [...new Set(positions)].filter(position => position >= 1 && position <= sequenceMap!.sequence.length);
  if (!valid.length) return;
  sequenceCommittedPositions = valid;
  setSequenceHighlight(valid);
  const matched = valid.map(position => sequenceMap!.residues.find(residue => residue.position === position)).filter((residue): residue is SequenceResidue => !!residue);
  const evidence = sequenceAnnotations.filter(feature => feature.segments.some(segment => segment.label_asym_id === sequenceMap!.label_asym_id
    && valid.some(position => segment.start <= position && position <= segment.end)));
  selectionContext = matched.length === 1
    ? { structure_id: sequenceStructureId, pdb_id: sequencePdbId, ...matched[0], label_asym_id: sequenceMap.label_asym_id,
      auth_asym_id: sequenceMap.auth_asym_id, annotations: annotationsAt(sequenceAnnotations, sequenceMap.label_asym_id, matched[0].label_seq_id) }
    : { structure_id: sequenceStructureId, pdb_id: sequencePdbId, label_asym_id: sequenceMap.label_asym_id,
      auth_asym_id: sequenceMap.auth_asym_id, selected_positions: valid,
      residues_with_coordinates: matched.filter(residue => residue.has_coordinates).length,
      annotations: evidence, selected_residues: matched };
  if (contextExtras) selectionContext = { ...selectionContext, ...contextExtras };
  const coordinates = valid.flatMap(position => residuePositions(sequenceCoordinates!, sequenceMap!.label_asym_id, position));
  const loci = sequenceLoci(valid);
  if (viewer) {
    if (loci) viewer.plugin.managers.interactivity.lociSelects.selectOnly({ loci });
    else viewer.plugin.managers.interactivity.lociSelects.deselectAll();
  }
  if (source === "focus" && coordinates.length && viewer) viewer.plugin.managers.camera.focusSpheres(coordinates, center => ({ center, radius: 2 }), { minRadius: 8 });
  const missing = matched.filter(residue => !residue.has_coordinates).length;
  const evidenceLabels = [...new Set(evidence.map(feature => `${feature.source}: ${feature.name}`))];
  el("sequence-detail").textContent = `${valid.length === 1 ? `${matched[0]?.letter ?? "?"} · label position ${valid[0]}` : `${valid.length} selected residues`}${missing ? ` · ${missing} without coordinates` : ""}${evidenceLabels.length ? ` · ${evidenceLabels.join("; ")}` : ""}`;
  showSequenceTooltip(valid, annotation, tooltipTarget, true);
  el<HTMLButtonElement>("sequence-focus").disabled = !coordinates.length;
  el<HTMLButtonElement>("sequence-clear").disabled = false;
  el("selection").textContent = typeof selectionContext.auth_seq_id === "number"
    ? `${matched[0].comp_id} · author chain ${sequenceMap.auth_asym_id} residue ${matched[0].auth_seq_id}${matched[0].insertion_code} · label chain ${sequenceMap.label_asym_id} residue ${matched[0].label_seq_id}${missing ? " · coordinates unavailable" : ""}`
    : `${valid.length} residues selected · label chain ${sequenceMap.label_asym_id}${missing ? ` · ${missing} without coordinates` : ""}`;
  workspaceControls();
  void publish({ status: "selection", selection: selectionContext });
}

function renderDynamicSequenceTracks(sequence: LinkedSequence) {
  const container = el("sequence-tracks"); container.replaceChildren();
  sequenceTrackFeaturePositions = new Map();
  sequenceTrackFeatureAnnotations = new Map();
  const palette = ["#16856a", "#d47532", "#6a76b8", "#c76b78", "#527fc1", "#9473bc", "#609c5d"];
  const dataGroups: { id: string; label: string; features: NightingaleFeature[] }[] = [];
  const observed = observedTrack(sequence);
  const annotationGroups = annotationTrackGroups(sequenceAnnotations, sequence.label_asym_id, sequence.residues.length);
  const category = (group: typeof annotationGroups[number]) => {
    const matching = group.features.map(feature => sequenceAnnotations.find(annotation => annotation.id === feature.accession)).filter((annotation): annotation is import("./annotations").Annotation => !!annotation);
    const text = matching.map(annotation => `${annotation.source} ${annotation.kind} ${annotation.accession} ${annotation.name} ${annotation.description}`).join(" ").toLowerCase();
    if (/uniprot/.test(text) && !/domain/.test(text)) return 0;
    if (/domain/.test(text)) return 2;
    if (/\bkb\b|knowledge.?base/.test(text) || matching.some(annotation => /^annotations?$/i.test(annotation.kind.trim()))) return 3;
    return -1;
  };
  const selectedGroups = annotationGroups.filter(group => category(group) >= 0)
    .sort((a, b) => category(a) - category(b) || a.label.localeCompare(b.label));
  dataGroups.push(...selectedGroups.filter(group => category(group) === 0));
  if (observed.length) dataGroups.push({ id: "observed_residues", label: "Observed residues", features: observed });
  dataGroups.push(...selectedGroups.filter(group => category(group) === 2 || category(group) === 3));
  sequenceTrackCatalog = dataGroups.map(group => ({ id: group.id, label: group.label, feature_count: group.features.length }));
  const shownGroups = sequenceTrackSelection ? dataGroups.filter(group => sequenceTrackSelection!.has(group.id)) : dataGroups;
  el<HTMLButtonElement>("sequence-show-all").disabled = !sequenceTrackSelection;
  for (const [index, group] of shownGroups.entries()) {
    const heading = document.createElement("div"); heading.className = "sequence-track-header";
    const title = document.createElement("h3"); title.textContent = group.label;
    title.className = "sequence-track-title"; heading.append(title);
    if (group.id !== "observed_residues") {
      const annotationIds = new Set(group.features.map(feature => feature.accession));
      const active = activeWorkspaceScene();
      const matchingLayers = active?.layers.filter(layer => layerCategory(layer) === "annotations"
        && layer.structure_id === sequenceStructureId
        && (layer.source_annotation_ids?.some(id => annotationIds.has(id))
          || (!!layer.source_annotation_id && annotationIds.has(layer.source_annotation_id)))) ?? [];
      const enabled = matchingLayers.length > 0 && matchingLayers.every(layer => layer.visible);
      const toggle = document.createElement("button");
      toggle.type = "button"; toggle.className = "sequence-track-3d-toggle";
      toggle.textContent = enabled ? "Hide in 3D" : "Show in 3D";
      toggle.disabled = matchingLayers.length === 0 || updating;
      toggle.setAttribute("aria-pressed", String(enabled));
      toggle.title = matchingLayers.length ? `Toggle ${group.label} annotation overlay in Mol*` : "No matching 3D annotation layer is available";
      toggle.addEventListener("click", () => {
        if (!active) return;
        const visible = !matchingLayers.every(layer => layer.visible);
        void mutate(matchingLayers.map(layer => ({ op: "set_visibility" as const, scene_id: active.id, target_id: layer.id, visible })));
      });
      heading.append(toggle);
    }
    const track = document.createElement("nightingale-track") as HTMLElement & { data: NightingaleFeature[] };
    track.setAttribute("length", String(sequence.residues.length)); track.setAttribute("height", "42");
    track.setAttribute("display-start", "1"); track.setAttribute("display-end", String(sequence.residues.length));
    track.setAttribute("layout", "non-overlapping"); track.setAttribute("aria-label", group.label);
    track.setAttribute("color", palette[index % palette.length]);
    const paintedFeatures: NightingaleFeature[] = [];
    for (const feature of group.features) {
      const annotation = sequenceAnnotations.find(item => item.id === feature.accession);
      const fragments = feature.locations.flatMap(location => location.fragments);
      fragments.forEach((fragment, fragmentIndex) => {
        const accession = fragments.length > 1 ? `${feature.accession}::segment-${fragmentIndex + 1}` : feature.accession;
        paintedFeatures.push({ ...feature, accession, locations: [{ fragments: [fragment] }] });
        sequenceTrackFeaturePositions.set(accession, Array.from({ length: fragment.end - fragment.start + 1 }, (_, index) => fragment.start + index));
        if (annotation) sequenceTrackFeatureAnnotations.set(accession, annotation);
      });
    }
    track.data = paintedFeatures;
    container.append(heading, track);
  }
  const structure = activeWorkspaceScene()?.structures.find(item => item.id === sequenceStructureId);
  if (!sequenceAnnotations.length && structure?.data_status?.annotations !== "loaded" && structure?.data_status?.annotations !== "unavailable") {
    const load = document.createElement("button");
    load.type = "button"; load.className = "sequence-load-annotations";
    load.textContent = "Load annotations";
    load.disabled = updating;
    load.addEventListener("click", () => { void toggleOptional("annotations", false, true); });
    container.append(load);
  }
  el("sequence-status").textContent = dataGroups.length
    ? `${sequence.residues.length} entity sequence positions · ${sequence.residues.filter(residue => residue.has_coordinates).length} with coordinates · ${sequenceTrackSelection ? `showing ${shownGroups.length} of ${dataGroups.length} available tracks` : `showing ${dataGroups.length} available tracks`}. Ask the assistant to select tracks for a question.`
    : structure?.data_status?.annotations === "unavailable" ? "No sequence tracks or annotation data are available for this chain."
    : "No sequence tracks are available for this chain.";
}

function renderSequencePanel() {
  if (!viewer || disposed || scene?.story) {
    el("sequence-panel").hidden = true; sequenceMap = undefined; sequenceCoordinates = undefined; sequenceTrackCatalog = [];
    sequenceTargetsByValue = new Map(); return;
  }
  const targets = sequenceTargets();
  sequenceTargetsByValue = new Map(targets.map(target => [target.value, target]));
  const select = el<HTMLSelectElement>("sequence-chain"), previous = select.value;
  select.replaceChildren(...targets.map(target => new Option(
    `${target.pdbId.toUpperCase()} · label ${target.chainId} / author ${target.authChainId} · ${target.sequence.residues.length} residues`, target.value)));
  if (!targets.length) {
    el("sequence-panel").hidden = true; sequenceMap = undefined; sequenceCoordinates = undefined; sequenceTrackCatalog = [];
    sequenceTargetsByValue = new Map(); return;
  }
  el("sequence-panel").hidden = !sequenceVisible;
  el<HTMLButtonElement>("sequence-toggle").textContent = sequenceVisible ? "Hide sequence" : "Show sequence";
  el<HTMLButtonElement>("sequence-toggle").setAttribute("aria-pressed", String(sequenceVisible));
  select.value = targets.some(target => target.value === previous) ? previous : targets[0].value;
  const target = sequenceTargetsByValue.get(select.value)!;
  sequenceStructureId = target.structureId; sequenceCoordinates = target.structure; sequencePdbId = target.pdbId;
  sequenceMap = target.sequence;
  const definition = activeWorkspaceScene()?.structures.find(structure => structure.id === target.structureId);
  sequenceAnnotations = definition?.annotations ?? [];
  const manager = el<HTMLElement>("sequence-manager");
  for (const element of [el<HTMLElement>("sequence-navigation"), el<HTMLElement>("nightingale-sequence")]) {
    element.setAttribute("length", String(target.sequence.residues.length));
    element.setAttribute("display-start", "1"); element.setAttribute("display-end", String(target.sequence.residues.length));
  }
  manager.setAttribute("length", String(target.sequence.residues.length));
  manager.setAttribute("display-start", "1"); manager.setAttribute("display-end", String(target.sequence.residues.length));
  const sequenceElement = el<HTMLElement>("nightingale-sequence") as HTMLElement & { sequence: string };
  sequenceElement.sequence = target.sequence.sequence;
  renderDynamicSequenceTracks(target.sequence);
  setSequenceHighlight(sequenceCommittedPositions);
}

function clearSequenceHover() {
  setSequenceHighlight(sequenceCommittedPositions);
  viewer?.plugin.managers.interactivity.lociHighlights.clearHighlights();
  if (!sequenceTooltipPinned) showSequenceTooltip([]);
}

function hoverSequencePositions(positions: number[]) {
  if (!sequenceMap) return;
  setSequenceHighlight(positions);
  const loci = sequenceLoci(positions);
  if (loci && viewer) viewer.plugin.managers.interactivity.lociHighlights.highlightOnly({ loci });
  else viewer?.plugin.managers.interactivity.lociHighlights.clearHighlights();
}

function handleNightingaleChange(event: Event) {
  const detail = (event as CustomEvent<{ eventType?: string; feature?: { position?: number; accession?: string; start?: number; end?: number } | null; target?: HTMLElement; "display-start"?: number; "display-end"?: number }>).detail;
  if (!detail) return;
  if (!detail.eventType) {
    if (typeof detail["display-start"] === "number" && typeof detail["display-end"] === "number" && sequenceMap) {
      const start = Math.max(1, Math.ceil(detail["display-start"]));
      const end = Math.min(sequenceMap.residues.length, Math.floor(detail["display-end"]));
      if (end >= start) showSequenceTooltip(Array.from({ length: end - start + 1 }, (_, index) => start + index), undefined, el("sequence-navigation"), true);
    }
    return;
  }
  if (detail.eventType === "mouseout") { clearSequenceHover(); return; }
  const feature = detail.feature;
  // Nightingale v5 reports the feature and clicked SVG target separately. For
  // disjoint annotations the SVG datum is the exact painted fragment.
  const painted = (detail.target as (HTMLElement & { __data__?: { start?: number; end?: number } }) | undefined)?.__data__;
  const start = painted?.start ?? feature?.start;
  const end = painted?.end ?? feature?.end ?? start;
  const positions = typeof feature?.position === "number" ? [feature.position]
    : typeof start === "number" ? Array.from({ length: Math.max(1, (end ?? start) - start + 1) }, (_, index) => start + index)
    : feature?.accession ? sequenceTrackFeaturePositions.get(feature.accession) ?? [] : [];
  if (detail.eventType === "mouseover") {
    if (positions.length) {
      hoverSequencePositions(positions);
      const annotation = feature?.accession ? sequenceTrackFeatureAnnotations.get(feature.accession) : undefined;
      showSequenceTooltip(positions, annotation, detail.target);
    }
    return;
  }
  if (detail.eventType === "click" && positions.length) {
    const annotation = feature?.accession ? sequenceTrackFeatureAnnotations.get(feature.accession) : undefined;
    selectSequencePositions(positions, "focus", annotation, detail.target);
  }
}

function setSequenceDisplayRange(start: number, end: number) {
  if (!sequenceMap) return;
  const length = sequenceMap.residues.length;
  const safeStart = Math.max(1, Math.min(length, start));
  const safeEnd = Math.max(safeStart, Math.min(length, end));
  for (const element of [el<HTMLElement>("sequence-manager"), el<HTMLElement>("sequence-navigation"), el<HTMLElement>("nightingale-sequence"), ...Array.from(el("sequence-tracks").querySelectorAll<HTMLElement>("nightingale-track"))]) {
    element.setAttribute("display-start", String(safeStart));
    element.setAttribute("display-end", String(safeEnd));
  }
}

function zoomSequence(factor: number) {
  if (!sequenceMap) return;
  const manager = el<HTMLElement>("sequence-manager");
  const length = sequenceMap.residues.length;
  const start = Number(manager.getAttribute("display-start") ?? 1);
  const end = Number(manager.getAttribute("display-end") ?? length);
  const width = end - start + 1;
  const nextWidth = Math.max(Math.min(length, 3), Math.min(length, width * factor));
  const center = (start + end) / 2;
  const nextStart = Math.floor(center - nextWidth / 2);
  setSequenceDisplayRange(nextStart, nextStart + Math.ceil(nextWidth) - 1);
}
async function mutate(operations: WorkspaceOperation[], prepare?: () => Promise<WorkspaceOperation[]>) {
  if (!workspace || updating) return;
  updating = true; workspaceControls(); status("Validating workspace update…");
  try {
    if (prepare) operations = await prepare();
    captureView();
    const compactSceneUpdate = operations.length > 0 && operations.every(operation => operation.op === "upsert_scene");
    const result = await app.callServerTool({ name: "ebi-pdbe-update_workspace", arguments: {
      workspace, expected_revision: workspace.revision, operations, compact_response: compactSceneUpdate,
    } });
    const visibilityOnly = operations.length > 0 && operations.every(operation => operation.op === "set_visibility");
    if (visibilityOnly) {
      if (result.isError) {
        status(result.content?.filter(item => item.type === "text").map(item => item.text).join("\n") || "Layer visibility update failed.", true);
        renderWorkspaceControls();
        return;
      }
      const update = result._meta?.visibility_update as { workspace_id?: string; revision?: number } | undefined;
      const mvsj = result._meta?.mvsj as Record<string, unknown> | undefined;
      if (!workspace || !scene || update?.workspace_id !== workspace.id
        || update.revision !== workspace.revision + 1 || !mvsj) {
        throw new Error("The server returned an invalid layer visibility update.");
      }
      const next = structuredClone(workspace);
      for (const operation of operations) {
        const targetScene = next.scenes.find(item => item.id === operation.scene_id);
        const layer = targetScene?.layers.find(item => item.id === operation.target_id);
        if (!layer || operation.visible === undefined) throw new Error("The layer visibility update did not match the current workspace.");
        layer.visible = operation.visible;
      }
      next.revision = update.revision;
      checkRevision(workspace, next);
      workspace = validateEnvelope(next);
      ligandWorkspaceSnapshot = workspace;
      scene.workspace = workspace;
      scene.mvsj = mvsj;
      const token = ++revision;
      buttons(false);
      work = work.then(() => load(scene!, token)).catch(error => status(String(error), true));
      await work;
      return;
    }
    if (compactSceneUpdate) {
      if (result.isError) {
        status(result.content?.filter(item => item.type === "text").map(item => item.text).join("\n") || "Workspace update failed.", true);
        renderWorkspaceControls();
        return;
      }
      const update = result._meta?.workspace_update as { workspace_id?: string; revision?: number } | undefined;
      const data = result._meta?.mvs as SceneResult | undefined;
      if (!workspace || !scene || update?.workspace_id !== workspace.id
        || update.revision !== workspace.revision + 1 || !data?.mvsj || data.version !== 1) {
        throw new Error("The server returned an invalid compact workspace update.");
      }
      const next = structuredClone(workspace);
      for (const operation of operations) {
        if (operation.op !== "upsert_scene" || !operation.scene || operation.scene.id !== operation.scene_id
          || operation.scene_id !== operation.target_id) {
          throw new Error("The compact workspace update did not match its scene operation.");
        }
        const index = next.scenes.findIndex(item => item.id === operation.scene_id);
        if (index < 0) next.scenes.push(operation.scene);
        else next.scenes[index] = operation.scene;
      }
      next.revision = update.revision;
      checkRevision(workspace, next);
      workspace = validateEnvelope(next);
      const updatedScene = workspace.scenes.find(item => item.id === operations[0].scene_id);
      const firstStructure = updatedScene?.structures[0];
      if (!updatedScene || !firstStructure) throw new Error("The compact update has no renderable structure.");
      const rendered: SceneResult = {
        version: 1,
        workspace,
        builder: { pdb_id: firstStructure.pdb_id, title: updatedScene.title },
        mvsj: data.mvsj,
        legend: [],
        warnings: data.warnings ?? workspace.warnings ?? [],
        coordinate_url: data.coordinate_url ?? scene.coordinate_url,
      };
      const token = ++revision;
      buttons(false);
      work = work.then(() => load(rendered, token)).catch(error => status(String(error), true));
      await work;
      return;
    }
    receive(result);
    if (result.isError) { renderWorkspaceControls(); return; }
    await work;
  } catch (error) { status(String(error), true); renderWorkspaceControls(); }
  finally { updating = false; workspaceControls(); }
}

async function toggleOptional(kind: OptionalData, visible: boolean, fetchIfMissing = false) {
  if (!workspace || !activeWorkspaceScene()) return;
  const originalId = workspace.id, originalRevision = workspace.revision;
  const base = structuredClone(activeWorkspaceScene()!);
  await mutate([], async () => {
    status(visible || fetchIfMissing ? `Loading optional ${kind}…` : `Hiding ${kind}…`);
    const pending = visible || fetchIfMissing ? base.structures.filter(structure => structure.data_status?.[kind] !== "loaded") : [];
    const fetched = await Promise.all(pending.map(async structure => {
      if (kind === "annotations") {
        const result = await app.callServerTool({ name: "ebi-pdbe-load_structure_annotations", arguments: { pdb_id: structure.pdb_id } });
        if (result.isError) throw new Error(result.content?.filter(item => item.type === "text").map(item => item.text).join("\n") || "Could not load annotations");
        const data = result.structuredContent as Omit<FetchedAnnotations, "structureId"> | undefined;
        if (!data || !Array.isArray(data.annotations) || !Array.isArray(data.layers)) throw new Error("The server did not return optional annotation data");
        return { structureId: structure.id, ...data } as FetchedAnnotations;
      }
      const result = await app.callServerTool({ name: "ebi-pdbe-open_structure", arguments: {
        pdb_id: structure.pdb_id, include_annotations: false, include_ligands: true,
      } });
      if (result.isError) throw new Error(result.content?.filter(item => item.type === "text").map(item => item.text).join("\n") || `Could not load ${kind}`);
      const supplied = result._meta?.workspace as Workspace | undefined;
      if (!supplied?.scenes?.[0]) throw new Error(`The server did not return optional ${kind} workspace data`);
      return { structureId: structure.id, scene: supplied.scenes[0] } as FetchedStructure;
    }));
    if (!workspace || workspace.id !== originalId || workspace.revision !== originalRevision
      || JSON.stringify(activeWorkspaceScene()) !== JSON.stringify(base)) throw new Error("Workspace changed while fetching data. Please retry with the current view.");
    const updated = kind === "annotations"
      ? mergeOptionalAnnotations(base, fetched as FetchedAnnotations[], visible)
      : mergeOptionalScene(base, fetched as FetchedStructure[], kind, visible);
    return [{ op: "upsert_scene", scene_id: updated.id, target_id: updated.id, scene: updated }];
  });
}
el<HTMLInputElement>("show-ligands").addEventListener("change", event => { void toggleOptional("ligands", (event.target as HTMLInputElement).checked); });

async function refreshDataView(token: number) {
  const active = activeWorkspaceScene();
  if (!viewer || !active || disposed || token !== revision) return;
  for (const definition of active.structures) {
    const coordinates = displayedStructure(viewer, definition.id);
    if (coordinates && !inventories.has(`${active.id}/${definition.id}`)) inventories.set(`${active.id}/${definition.id}`, coordinateInventory(coordinates));
  }
  const comparison = active.comparison;
  el("comparison-summary").textContent = comparison
    ? `${comparison.mapped_pair_count} residue pairs from PDBe/SIFTS · ${comparison.uniprot_accession} · segment ${comparison.segment.index}` : "";
  const rows = el("comparison-rows"); rows.replaceChildren();
  comparison?.pairs.forEach(pair => {
    const tr = document.createElement("tr");
    for (const text of [String(pair.uniprot_position),
      `${pair.reference.comp_id} · label ${pair.reference.label_seq_id} / author ${pair.reference.auth_seq_id ?? "?"}${pair.reference.insertion_code}`,
      `${pair.mobile.comp_id} · label ${pair.mobile.label_seq_id} / author ${pair.mobile.auth_seq_id ?? "?"}${pair.mobile.insertion_code}`]) {
      const td = document.createElement("td"); td.textContent = text; tr.append(td);
    }
    tr.tabIndex = 0; tr.setAttribute("role", "button");
    tr.setAttribute("aria-label", `Inspect UniProt residue ${pair.uniprot_position}`);
    const inspect = () => {
      if (!viewer || !comparison) return;
      selectionContext = { uniprot_position: pair.uniprot_position, reference: pair.reference, mobile: pair.mobile,
        method: comparison.method, sources: comparison.sources };
      const points = [[comparison.reference_id, comparison.reference.chain.label_asym_id, pair.reference.label_seq_id],
        [comparison.mobile_id, comparison.mobile.chain.label_asym_id, pair.mobile.label_seq_id]].flatMap(([id, chain, label]) => {
          const structure = displayedStructure(viewer!, String(id));
          return structure ? residuePositions(structure, String(chain), Number(label)) : [];
        });
      if (points.length) viewer.plugin.managers.camera.focusSpheres(points, center => ({ center, radius: 2 }), { minRadius: 8 });
      el("selection").textContent = `UniProt ${pair.uniprot_position} · PDBe/SIFTS residue correspondence`;
      void publish({ status: "selection", selection: selectionContext });
    };
    tr.addEventListener("click", inspect); tr.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); inspect(); } });
    rows.append(tr);
  });
  renderSequencePanel();
  workspaceControls();
}


function updateStoryControls(): void {
  const snapshots = viewer?.plugin.managers.snapshot;
  const busy = updating || !snapshots || snapshots.state.isPlaying || viewer?.plugin.behaviors.state.isBusy.value || navigating;
  for (const id of ["story-prev", "story-next"]) {
    el<HTMLButtonElement>(id).disabled = !!busy || (snapshots?.state.entries.size ?? 0) < 2;
  }
  const entry = snapshots?.getEntry(snapshots.state.current!);
  el("story-title").textContent = entry?.name ?? currentScene()?.title ?? "Story";
}

async function navigateStory(direction: -1 | 1): Promise<void> {
  if (!viewer || el<HTMLButtonElement>("story-next").disabled) return;
  navigating = true;
  updateStoryControls();
  try {
    await viewer.plugin.managers.snapshot.applyNext(direction);
  } catch (error) {
    status(`Could not change story scene: ${String(error)}`, true);
  } finally {
    navigating = false;
    updateStoryControls();
  }
}

function buttons(ready: boolean): void {
  el<HTMLButtonElement>("reset").disabled = !ready;
  el<HTMLButtonElement>("download").disabled = !ready;
  workspaceControls();
  if (!ready) {
    el<HTMLButtonElement>("story-prev").disabled = true;
    el<HTMLButtonElement>("story-next").disabled = true;
  }
}

function currentScene() {
  return scene?.scenes?.find(item => item.id === viewer?.plugin.managers.snapshot.current?.key) ?? scene?.scenes?.[0];
}

function showSceneDetails(): void {
  const active = currentScene();
  const activeWorkspace = activeWorkspaceScene();
  const accessions = activeWorkspace?.structures.map(structure => structure.pdb_id)
    ?? [active?.builder.pdb_id ?? scene?.builder?.pdb_id];
  const pdbIds = [...new Set(accessions.filter((id): id is string => typeof id === "string" && !!id)
    .map(id => /^[a-z0-9]{4}$/i.test(id) ? `pdb_0000${id.toLowerCase()}` : id))];
  const identifiers = el("pdb-ids");
  identifiers.hidden = !pdbIds.length;
  identifiers.textContent = pdbIds.length ? `${pdbIds.length === 1 ? "PDB ID" : "PDB IDs"}: ${pdbIds.join(" · ")}` : "";
  const layers = activeWorkspace?.layers;
  const legend: LegendItem[] = layers ? layers.filter(layer => layer.visible && layerCategory(layer) !== "annotations").map(layer => {
    const definition = layer.component ?? layer.annotation;
    const colorSpecs = [definition?.["color"], ...(Array.isArray(definition?.["colors"]) ? definition["colors"] : [])];
    let colors: string[] = [];
    for (const value of colorSpecs) {
      const spec = value as { color?: string; selector?: unknown } | undefined;
      if (typeof spec?.color !== "string") continue;
      // Match builder ordering: an unconditional colour replaces earlier ones.
      if (spec.selector == null) colors = [];
      if (!colors.includes(spec.color)) colors.push(spec.color);
    }
    return { label: layer.name, colors,
      representation: String((definition?.["representation"] as { type?: string } | undefined)?.type ?? "cartoon") };
  }) : active?.legend ?? scene?.legend ?? [];
  el("legend").replaceChildren(...legend.map(item => {
    const li = document.createElement("li");
    const colors = [...new Set(item.colors ?? [])].filter(color => CSS.supports("color", color));
    for (const color of colors) {
      const swatch = document.createElement("span");
      swatch.className = "legend-swatch";
      swatch.style.backgroundColor = color;
      swatch.title = `Highlight color: ${color}`;
      swatch.setAttribute("aria-hidden", "true");
      li.append(swatch);
    }
    const label = document.createElement("span");
    label.textContent = `${item.label} · ${item.representation.replaceAll("_", " ")}`;
    li.append(label);
    if (colors.length) li.setAttribute("aria-label", `${label.textContent}; highlight colors: ${colors.join(", ")}`);
    return li;
  }));
  el("source").textContent = `Coordinates: ${active?.coordinate_url ?? scene?.coordinate_url ?? ""}`;

}

function captureView() {
  const active = activeWorkspaceScene(), camera = viewer?.plugin.canvas3d?.camera.state;
  if (workspace && active && camera) {
    workspace.view ??= { cameras: {} };
    workspace.view.active_scene_id = active.id;
    workspace.view.cameras[active.id] = { position: [...camera.position], target: [...camera.target], up: [...camera.up] };
  }
}
async function publish(data: Record<string, unknown>): Promise<void> {
  captureView();
  workspaceControls();
  if (connected && !disposed && app.getHostCapabilities()?.updateModelContext) {
    try {
      await app.updateModelContext({ structuredContent: { pdbe_mvs: data,
        pdbe_workspace: workspace ? { workspace, status: loadState, active_scene_id: activeWorkspaceScene()?.id,
          selection: selectionContext ?? null,
          available_ligands: activeWorkspaceScene()?.structures.map(structure => ({ structure_id: structure.id, ligands: availableLigands(structure) })),
          scientific_policy: "supplied_data_only",
          source_annotations: activeWorkspaceScene()?.structures.map(structure => ({ structure_id: structure.id, annotations: structure.annotations ?? [] })),
          comparison: activeWorkspaceScene()?.comparison ?? null,
        } : null,
        pdbe_sequence_track_capabilities: sequenceMap ? {
          workspace_id: workspace?.id ?? null,
          structure_id: sequenceStructureId,
          pdb_id: sequencePdbId,
          label_asym_id: sequenceMap.label_asym_id,
          auth_asym_id: sequenceMap.auth_asym_id,
          sequence_length: sequenceMap.sequence.length,
          tracks: sequenceTrackCatalog,
          selected_tracks: sequenceTrackSelection ? [...sequenceTrackSelection] : "all",
          instruction: "Choose the sequence tracks that best answer the user's question. Use ebi-pdbe-set_sequence_tracks with these exact IDs and workspace/structure/chain identifiers; the app can render observed-residue coverage and supplied annotation groups. Do not infer unsupported tracks or scientific facts.",
        } : null } });
    } catch (error) {
      // Host context is optional; its failure must not misreport a rendered scene.
      console.warn("Could not update the host's molecular scene context", error);
    }
  }
}

async function load(result: SceneResult, token: number): Promise<void> {
  if (disposed || token !== revision) return;
  const preserve = workspace?.id === result.workspace?.id && !!workspace;
  const previousScene = activeWorkspaceScene()?.id;
  scene = result; workspace = result.workspace; renderedMvs = structuredClone(result.mvsj);
  if (workspace) {
    if (renderedMvs.kind === "multiple") (renderedMvs.snapshots as { root: SceneNode }[]).forEach((snapshot, index) => attachLayerRefs(snapshot.root, workspace!.scenes[index].layers));
    else attachLayerRefs(renderedMvs.root as SceneNode, workspace.scenes[0].layers);
  }
  inventories = new Map();
  if (!preserve) { sequenceTrackSelection = undefined; sequenceCommittedPositions = []; }
  if (!preserve || selectionContext?.structure_id && !workspace?.scenes.some(s => s.structures.some(structure => structure.id === selectionContext!.structure_id))
      || selectionContext?.uniprot_position && !workspace?.scenes.some(s => s.comparison)) selectionContext = undefined;
  loadState = "loading";
  el("story-panel").hidden = !result.story;
  el("story-layout").classList.toggle("has-story", !!result.story);
  buttons(false);
  status("Loading coordinates and constructing the molecular view…");
  el("title").textContent = result.story?.title ?? result.builder?.title ?? "Molecular view";
  el("description").textContent = result.story?.description ?? result.builder?.description ?? "";
  el("warnings").textContent = result.warnings.join(" ");
  el("selection").textContent = "Select a residue or atom to inspect it.";
  showSceneDetails();
  try {
    if (!preserve) { viewer?.dispose(); viewer = undefined; el("viewer").replaceChildren(); }
    const created = viewer ?? await createWorkspaceViewer(el("viewer"), el("story-text"), () => !!scene?.story);
    if (disposed || token !== revision) { if (created !== viewer) created.dispose(); return; }
    const isNewViewer = viewer !== created;
    viewer = created;
    if (isNewViewer) created.subscribe(created.plugin.behaviors.state.isBusy, updateStoryControls);
    const snapshotIndex = Math.max(0, workspace?.scenes.findIndex(s => s.id === (preserve ? previousScene : workspace?.view?.active_scene_id)) ?? 0);
    await created.loadMvsData(JSON.stringify(renderedMvs), "mvsj", { sanityChecks: true, keepCamera: preserve, defaultSnapshotIndex: snapshotIndex });
    await refreshDataView(token);
    if (ligandData?.selected) highlightContact({ end: {
      chain_id: String(ligandData.selected.auth_asym_id), label_asym_id: String(ligandData.selected.label_asym_id),
      author_residue_number: ligandData.selected.auth_seq_id as string | number,
      author_insertion_code: String(ligandData.selected.insertion_code ?? ""), chem_comp_id: String(ligandData.selected.comp_id),
    } });
    if (disposed || token !== revision) return;
    const structures = created.plugin.managers.structure.hierarchy.current.structures;
    const atomCount = structures.reduce((count, s) => count + (s.cell.obj?.data.elementCount ?? 0), 0);
    const components = structures.flatMap(s => s.components);
    const empty = components.filter(c => !c.cell.obj?.data.elementCount).length;
    const hasVisibleAtoms = components.some(c => (c.cell.obj?.data.elementCount ?? 0) > 0);
    loadState = hasVisibleAtoms ? "loaded" : "empty";
    renderWorkspaceControls();
    const allHidden = activeWorkspaceScene()?.layers.every(layer => !layer.visible);
    const message = allHidden ? "All visual layers are hidden. Enable a layer to show the structure." : atomCount === 0 ? "The coordinates loaded, but no atoms are available in this structure."
      : empty ? `Scene loaded. ${empty} selection(s) contain no atoms; check chain IDs and residue numbering.`
      : "Molecular view ready. Rotate, zoom, or select a residue to inspect it.";
    status(message, !allHidden && (atomCount === 0 || empty > 0));
    await publish({ status: hasVisibleAtoms ? "loaded" : "empty", pdb_id: currentScene()?.builder.pdb_id ?? result.builder?.pdb_id, atom_count: atomCount, empty_components: empty });
    if (isNewViewer) created.subscribe(created.plugin.managers.snapshot.events.changed, () => {
      if (disposed || loadState === "loading") return;
      showSceneDetails();
      updateStoryControls();
      const active = currentScene();
      if (active) {
        const currentToken = revision;
        work = work.then(async () => {
          await refreshDataView(currentToken); renderWorkspaceControls();
          await publish({ status: "story_scene", scene_id: active.id, pdb_id: active.builder.pdb_id, playing: created.plugin.managers.snapshot.state.isPlaying });
        }).catch(error => status(String(error), true));
      }
    });
    showSceneDetails();
    updateStoryControls();
    if (isNewViewer) created.subscribe(created.plugin.behaviors.interaction.click, event => {
      if (!StructureElement.Loci.is(event.current.loci) || StructureElement.Loci.isEmpty(event.current.loci)) return;
      const loci = event.current.loci;
      const first = loci.elements[0];
      const location = StructureElement.Location.create(loci.structure, first.unit, first.unit.elements[OrderedSet.getAt(first.indices, 0)]);
      const p = StructureProperties;
      const selectedStructure = activeWorkspaceScene()?.structures.find(s => displayedStructure(created, s.id)?.units.includes(first.unit));
      const selection = {
        structure_id: selectedStructure?.id,
        pdb_id: selectedStructure?.pdb_id ?? currentScene()?.builder.pdb_id ?? scene?.builder?.pdb_id,
        label_asym_id: p.chain.label_asym_id(location), auth_asym_id: p.chain.auth_asym_id(location),
        label_seq_id: p.residue.label_seq_id(location) > 0 ? p.residue.label_seq_id(location) : null, auth_seq_id: p.residue.auth_seq_id(location),
        insertion_code: p.residue.pdbx_PDB_ins_code(location), comp_id: p.atom.label_comp_id(location),
        atom_id: p.atom.label_atom_id(location), instance_id: location.unit.conformation.operator.instanceId,
        model_id: location.unit.model.modelNum,
      };
      let sequenceSynced = false;
      selectionContext = { ...selection, annotations: selectedStructure ? annotationsAt(selectedStructure.annotations ?? [], selection.label_asym_id, selection.label_seq_id) : [] };
      if (selection.label_seq_id !== null && selectedStructure) {
        const target = sequenceTargets().find(item => item.structureId === selectedStructure.id && item.chainId === selection.label_asym_id);
        if (target) {
          el<HTMLSelectElement>("sequence-chain").value = target.value;
          renderSequencePanel();
          selectSequencePositions([selection.label_seq_id], "focus", undefined, undefined, selection);
          sequenceSynced = true;
        }
      }
      el("selection").textContent = `${selection.comp_id} · author chain ${selection.auth_asym_id} residue ${selection.auth_seq_id}${selection.insertion_code} · label chain ${selection.label_asym_id}${selection.label_seq_id === null ? "" : ` residue ${selection.label_seq_id}`}`;
      if (!sequenceSynced) void publish({ status: "selection", selection }).catch(error => status(String(error), true));
    });
    if (isNewViewer) created.subscribe(created.plugin.behaviors.interaction.hover, event => {
      if (!sequenceMap || !sequenceCoordinates || !StructureElement.Loci.is(event.current.loci)
        || StructureElement.Loci.isEmpty(event.current.loci)) { clearSequenceHover(); return; }
      const loci = event.current.loci, first = loci.elements[0];
      if (!sequenceCoordinates.units.includes(first.unit)) { clearSequenceHover(); return; }
      const location = StructureElement.Location.create(loci.structure, first.unit, first.unit.elements[OrderedSet.getAt(first.indices, 0)]);
      const chain = StructureProperties.chain.label_asym_id(location);
      const position = StructureProperties.residue.label_seq_id(location);
      if (chain === sequenceMap.label_asym_id && position > 0) hoverSequencePositions([position]);
      else clearSequenceHover();
    });
    buttons(true);
  } catch (error) {
    if (disposed || token !== revision) return;
    const message = error instanceof Error ? error.message : String(error);
    loadState = "error"; workspaceControls();
    status(`Could not load the molecular view: ${message}`, true);
    // A valid artifact remains downloadable even when coordinate retrieval fails.
    buttons(true);
    await publish({ status: "error", pdb_id: currentScene()?.builder.pdb_id ?? result.builder?.pdb_id, error: message });
  }
}

function contactClassifications(record: ContactRecord): string[] {
  const values = Array.isArray(record.interaction_details) ? record.interaction_details : [record.interaction_details];
  return [...new Set(values.filter((value): value is string => typeof value === "string" && value.length > 0))];
}
function contactPartnerType(record: ContactRecord): string {
  const comp = String(record.end?.chem_comp_id ?? "").toUpperCase();
  if (["HOH", "WAT", "DOD"].includes(comp)) return "water";
  if (/^(MG|MN|FE|ZN|CU|CO|NI|CA|NA|K|CD|HG|CL|IOD|BR)$/.test(comp)) return "metal";
  const chain = ligandData?.chains?.find(item => item.auth_asym_id === record.end?.chain_id);
  const kind = String(chain?.molecule_type ?? "").toLowerCase();
  if (kind.includes("polypeptide") || kind === "protein") return "protein";
  if (kind === "water") return "water";
  return "other";
}
function contactPartnerName(record: ContactRecord): string {
  const chain = ligandData?.chains?.find(item => item.auth_asym_id === record.end?.chain_id);
  return typeof chain?.name === "string" ? chain.name : "name unavailable";
}
function ligandRoleText(value: unknown): string[] {
  const labels = new Set<string>();
  const semanticKeys = new Set(["role", "type", "category", "annotation", "label", "name", "function", "classification"]);
  const add = (raw: string) => {
    const label = raw.replaceAll("_", " ").replace(/\s+/g, " ").trim();
    if (label) labels.add(label[0].toUpperCase() + label.slice(1));
  };
  const visit = (current: unknown) => {
    if (typeof current === "string") { add(current); return; }
    if (Array.isArray(current)) { current.forEach(item => visit(item)); return; }
    if (!current || typeof current !== "object") return;
    const entries = Object.entries(current as Record<string, unknown>);
    const semantic = entries.filter(([key]) => semanticKeys.has(key.toLowerCase()));
    for (const [key, item] of semantic.length ? semantic : entries) {
      if (item === true) add(key);
      else if (typeof item === "string" && !semantic.length) add(`${key}: ${item}`);
      else visit(item);
    }
  };
  visit(value);
  return [...labels];
}
function filteredContacts(): ContactRecord[] {
  if (!ligandData) return [];
  const classification = el<HTMLSelectElement>("contact-classification").value;
  const interactionType = el<HTMLSelectElement>("contact-interaction-type").value;
  const chain = el<HTMLSelectElement>("contact-chain").value;
  const type = el<HTMLSelectElement>("contact-type").value;
  const maximum = Number(el<HTMLInputElement>("contact-max-distance").value);
  const matching = ligandData.contacts.filter(record => {
    if (classification && !contactClassifications(record).includes(classification)) return false;
    if (interactionType && record.interaction_type !== interactionType) return false;
    if (chain && record.end?.chain_id !== chain) return false;
    if (type && contactPartnerType(record) !== type) return false;
    return true;
  });
  const geometryTypes = new Set(matching.map(record => record.interaction_type ?? "unknown"));
  const distanceInput = el<HTMLInputElement>("contact-max-distance");
  const distanceStatus = el("contact-distance-status");
  distanceInput.disabled = geometryTypes.size > 1;
  distanceStatus.textContent = geometryTypes.size > 1
    ? "Unavailable for mixed interaction geometries; source distance values remain visible. Filter to records with one source interaction type first."
    : "Applies to source-reported numeric distances for the currently matching interaction type.";
  if (!distanceInput.value || geometryTypes.size > 1) return matching;
  return matching.filter(record => !Number.isFinite(Number(record.distance)) || Number(record.distance) <= maximum);
}
function csvCell(value: unknown): string { return `"${String(value ?? "").replaceAll('"', '""')}"`; }
function contactCsv(records: ContactRecord[]): string {
  const columns = ["pdb_id", "ccd_id", "ligand_label_chain", "ligand_auth_chain", "ligand_auth_residue", "ligand_insertion_code", "ligand_atoms", "partner_auth_chain", "partner_auth_residue", "partner_insertion_code", "partner_comp_id", "partner_atoms", "interaction_type", "classifications", "pdbe_distance_angstrom", "source_endpoint", "retrieved_at"];
  const rows = records.map(record => [ligandData?.pdb_id, ligandData?.selected?.comp_id, ligandData?.selected?.label_asym_id, ligandData?.selected?.auth_asym_id,
    ligandData?.selected?.auth_seq_id, ligandData?.selected?.insertion_code, record.ligand_atoms, record.end?.chain_id,
    record.end?.author_residue_number, record.end?.author_insertion_code, record.end?.chem_comp_id, record.end?.atom_names,
    record.interaction_type, record.interaction_details, record.distance, ligandData?.interaction_source, ligandData?.retrieved_at]);
  return [columns, ...rows].map(row => row.map(value => csvCell(Array.isArray(value) ? JSON.stringify(value) : value)).join(",")).join("\r\n");
}
function highlightContact(record: ContactRecord): void {
  if (!viewer || !record.end) return;
  const matches: { structure: import("molstar-mvs/lib/mol-model/structure/structure.js").Structure; unit: any; indices: number[] }[] = [];
  for (const current of viewer.plugin.managers.structure.hierarchy.current.structures) {
    const structure = current.cell.obj?.data;
    if (!structure) continue;
    for (const unit of structure.units) {
      const model = unit.model, h = model.atomicHierarchy, indices: number[] = [];
      for (let offset = 0; offset < unit.elements.length; offset++) {
        const atom = unit.elements[offset], ri = h.residueAtomSegments.index[atom], ci = h.chainAtomSegments.index[atom];
        if (h.chains.auth_asym_id.value(ci) !== record.end.chain_id
          || String(h.residues.auth_seq_id.value(ri)) !== String(record.end.author_residue_number)
          || (h.residues.pdbx_PDB_ins_code.value(ri) || "").trim() !== (record.end.author_insertion_code || "").trim()) continue;
        if (record.end.label_asym_id && h.chains.label_asym_id.value(ci) !== record.end.label_asym_id) continue;
        if (record.end.chem_comp_id && h.atoms.label_comp_id.value(atom) !== record.end.chem_comp_id) continue;
        const name = h.atoms.label_atom_id.value(atom);
        const atomNames = (record.end.atom_names ?? []).flatMap(value => value.split(",").map(part => part.trim()));
        if (!atomNames.length || atomNames.includes(name)) indices.push(offset);
      }
      if (indices.length) matches.push({ structure, unit, indices });
    }
  }
  // The endpoint lacks assembly/model identifiers; never choose among duplicate coordinate copies.
  if (matches.length !== 1) { status("This contact cannot be mapped to one coordinate copy from the source identifiers."); return; }
  const match = matches[0];
  const loci = StructureElement.Loci(match.structure, [{ unit: match.unit, indices: OrderedSet.ofSortedArray(matches[0].indices as UnitIndex[]) }]);
  viewer.plugin.managers.interactivity.lociHighlights.highlightOnly({ loci });
}
function renderLigandData(data: LigandData): void {
  ligandData = data;
  const panel = el("ligand-interaction-panel"); panel.hidden = false;
  const input = el<HTMLInputElement>("ligand-pdb-id"); input.value = data.pdb_id;
  const select = el<HTMLSelectElement>("ligand-instance"), previous = data.selected
    ? JSON.stringify([data.selected.comp_id, data.selected.auth_asym_id, data.selected.auth_seq_id, data.selected.insertion_code, data.selected.label_asym_id]) : "";
  select.replaceChildren(new Option("Choose a ligand instance…", ""));
  data.ligands.forEach((item, index) => {
    const identity = [item.comp_id, item.auth_asym_id, item.auth_seq_id, item.insertion_code ?? "", item.label_asym_id];
    const roles = ligandRoleText(item.role_annotations);
    const roleLabel = roles.length ? ` · roles ${roles.join(", ")}` : "";
    const bound = item.bound_molecule_id ? ` · bound molecule ${item.bound_molecule_id}` : "";
    select.add(new Option(`${item.comp_id} · author chain ${item.auth_asym_id} · residue ${item.auth_seq_id}${item.insertion_code ?? ""} · label chain ${item.label_asym_id}${item.label_seq_id == null ? "" : ` · label residue ${item.label_seq_id}`} · alternate conformers ${item.alternate_conformers ?? "unavailable"}${bound}${roleLabel}`, JSON.stringify(identity)));
    if (JSON.stringify(identity) === previous) select.selectedIndex = index + 1;
  });
  select.disabled = false;
  const controls = el("ligand-filter-controls"); controls.hidden = !data.selected;
  const classes = [...new Set(data.contacts.flatMap(contactClassifications))].sort();
  const classSelect = el<HTMLSelectElement>("contact-classification"), oldClass = classSelect.value;
  classSelect.replaceChildren(new Option("All classifications", ""), ...classes.map(value => new Option(value, value)));
  if (classes.includes(oldClass)) classSelect.value = oldClass;
  const interactionTypes = [...new Set(data.contacts.map(record => record.interaction_type).filter((value): value is string => !!value))].sort();
  const recordTypeSelect = el<HTMLSelectElement>("contact-interaction-type"), oldRecordType = recordTypeSelect.value;
  recordTypeSelect.replaceChildren(new Option("All interaction types", ""), ...interactionTypes.map(value => new Option(value, value)));
  if (interactionTypes.includes(oldRecordType)) recordTypeSelect.value = oldRecordType;
  const chains = [...new Set(data.contacts.map(record => record.end?.chain_id).filter((value): value is string => !!value))].sort();
  const chainSelect = el<HTMLSelectElement>("contact-chain"), oldChain = chainSelect.value;
  chainSelect.replaceChildren(new Option("All chains", ""), ...chains.map(value => new Option(value, value)));
  if (chains.includes(oldChain)) chainSelect.value = oldChain;
  const statusText = data.selected ? `${data.contacts.length} source interaction records for ${data.selected.comp_id}; source distance convention may vary by interaction category.` : `${data.ligands.length} ligand instances. Select by CCD, author chain, residue and insertion code.`;
  el("ligand-evidence-status").textContent = statusText;
  const evidence = el("ligand-evidence"); evidence.replaceChildren();
  const sources = [...(data.entry_sources ?? []), data.interaction_source, data.validation_source, data.assembly_source].filter((value): value is string => !!value);
  for (const source of sources) { const p = document.createElement("p"); p.textContent = `Source: ${source}`; evidence.append(p); }
  const when = document.createElement("p"); when.textContent = `Retrieved: ${data.retrieved_at}`; evidence.append(when);
  const validation = document.createElement("pre"); validation.textContent = data.validation == null ? "Ligand validation: unavailable" : JSON.stringify(data.validation, null, 2); evidence.append(validation);
  const assembly = document.createElement("pre"); assembly.textContent = data.assembly_context == null ? "Assembly composition: unavailable" : `Assembly context\n${JSON.stringify(data.assembly_context, null, 2)}`; evidence.append(assembly);
  const lineStatus = document.createElement("p"); lineStatus.textContent = data.contact_lines_enabled ? "Contact lines are available for unambiguous source mappings." : `Contact lines unavailable: ${data.contact_lines_unavailable_reason ?? "source mapping is ambiguous"}`; evidence.append(lineStatus);
  const ligandRoles = ligandRoleText(data.selected?.role_annotations);
  const roleText = document.createElement("p"); roleText.textContent = `Ligand roles: ${ligandRoles.length ? ligandRoles.join(", ") : data.selected?.role_annotations === undefined ? "unavailable" : "none reported"}`; evidence.append(roleText);
  const classificationNote = document.createElement("p"); classificationNote.textContent = "Interaction classifications below are PDBe-distributed computational records. Curated functional annotations are separate supporting context."; evidence.append(classificationNote);
  const annotations = data.annotations ?? [];
  if (annotations.length) {
    const heading = document.createElement("p"); heading.textContent = `Available residue and binding-site annotations (${annotations.length})`; evidence.append(heading);
    for (const annotation of annotations.slice(0, 80)) {
      const record = annotation as Record<string, unknown>, item = document.createElement("details"), summary = document.createElement("summary");
      summary.textContent = `${String(record.source ?? "PDBe annotation")} · ${String(record.name ?? record.accession ?? "supporting context")}`;
      const value = document.createElement("pre"); value.textContent = JSON.stringify(record, null, 2); item.append(summary, value); evidence.append(item);
    }
  }
  const notes = document.createElement("p"); notes.textContent = data.warnings?.length ? data.warnings.join(" ") : "Conservation and functional annotations are supporting context only. Missing annotation data is unavailable, never inferred."; evidence.append(notes);
  try { localStorage.setItem(`pdbe-ligand-workflow:${data.pdb_id}`, JSON.stringify({ data, workspace: ligandWorkspaceSnapshot, filters: {
    classification: classSelect.value, interactionType: el<HTMLSelectElement>("contact-interaction-type").value, chain: chainSelect.value, type: el<HTMLSelectElement>("contact-type").value,
    maxDistance: el<HTMLInputElement>("contact-max-distance").value,
  } })); } catch { /* Storage can be disabled by the host. */ }
  renderContactRows();
}
function renderContactRows(): void {
  const body = el("contact-rows"), records = filteredContacts(); body.replaceChildren();
  for (const record of records) {
    const row = document.createElement("tr"); row.tabIndex = 0; row.setAttribute("role", "button");
    const partner = record.end ?? {};
    [ `${partner.chem_comp_id ?? "?"} · ${partner.chain_id ?? "?"}:${partner.author_residue_number ?? "?"}${partner.author_insertion_code?.trim() ?? ""} (${contactPartnerType(record)} · ${contactPartnerName(record)})`,
      JSON.stringify(record.ligand_atoms ?? []), JSON.stringify(partner.atom_names ?? []), record.interaction_type,
      contactClassifications(record).join("; "), record.distance ].forEach(value => { const cell = document.createElement("td"); cell.textContent = String(value ?? "unavailable"); row.append(cell); });
    row.addEventListener("click", () => highlightContact(record));
    row.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); highlightContact(record); } });
    body.append(row);
  }
  el<HTMLButtonElement>("export-contacts").disabled = !records.length;
  if (ligandData) {
    try { localStorage.setItem(`pdbe-ligand-workflow:${ligandData.pdb_id}`, JSON.stringify({ data: ligandData, workspace: ligandWorkspaceSnapshot,
      filters: { classification: el<HTMLSelectElement>("contact-classification").value, interactionType: el<HTMLSelectElement>("contact-interaction-type").value, chain: el<HTMLSelectElement>("contact-chain").value,
        type: el<HTMLSelectElement>("contact-type").value, maxDistance: el<HTMLInputElement>("contact-max-distance").value } })); }
    catch { /* Storage can be disabled by the host. */ }
  }
}

function receive(result: ToolResult): void {
  const suppliedWorkspace = result._meta?.workspace ?? (result._meta?.mvs as SceneResult | undefined)?.workspace;
  if (suppliedWorkspace) ligandWorkspaceSnapshot = suppliedWorkspace as Workspace;
  const ligandResult = result._meta?.ligand_data as LigandData | undefined;
  if (ligandResult) renderLigandData(ligandResult);
  if (suppliedWorkspace) {
    try {
      const next = validateEnvelope(suppliedWorkspace); checkRevision(workspace, next);
    } catch (error) { status(String(error), true); return; }
  }
  if (result.isError) {
    status(result.content?.filter(c => c.type === "text").map(c => c.text).join("\n") || "Scene construction failed.", true);
    return;
  }
  const trackConfig = result._meta?.sequence_track_config as {
    workspace_id?: string | null; structure_id: string; pdb_id: string; label_asym_id: string; track_ids: string[]; reason?: string;
  } | undefined;
  if (trackConfig) {
    const currentTarget = sequenceTargetsByValue.get(JSON.stringify([trackConfig.structure_id, trackConfig.label_asym_id]));
    if (!currentTarget || (trackConfig.workspace_id ?? undefined) !== (workspace?.id ?? undefined)
      || currentTarget.pdbId.toLowerCase() !== trackConfig.pdb_id.toLowerCase()) {
      status("Ignored a sequence-track choice for a different or outdated structure/chain.", true);
      return;
    }
    const available = new Set(sequenceTrackCatalog.map(track => track.id));
    const unknown = trackConfig.track_ids.filter(id => !available.has(id));
    if (unknown.length) {
      status(`Ignored unknown sequence track ID(s): ${unknown.join(", ")}`, true);
      return;
    }
    const targetValue = JSON.stringify([trackConfig.structure_id, trackConfig.label_asym_id]);
    if (el<HTMLSelectElement>("sequence-chain").value !== targetValue) {
      viewer?.plugin.managers.interactivity.lociSelects.deselectAll();
      sequenceCommittedPositions = []; selectionContext = undefined;
    }
    el<HTMLSelectElement>("sequence-chain").value = targetValue;
    sequenceTrackSelection = new Set(trackConfig.track_ids);
    renderSequencePanel();
    const detail = trackConfig.reason ? ` ${trackConfig.reason}` : "";
    status(`Assistant selected ${trackConfig.track_ids.length} sequence track(s).${detail}`);
    void publish({ status: "sequence_tracks_selected", track_ids: trackConfig.track_ids, reason: trackConfig.reason });
    return;
  }
  const data = result._meta?.mvs as SceneResult | undefined;
  if (!data?.mvsj || data.version !== 1 || !(data.builder && Array.isArray(data.legend) || data.story && Array.isArray(data.scenes))) {
    status("No supported MVS scene was returned by the tool.", true);
    return;
  }
  const token = ++revision;
  buttons(false);
  data.workspace = result._meta?.workspace as Workspace | undefined ?? data.workspace;
  work = work.then(() => load(data, token)).catch(error => status(String(error), true));
}

el("reset").addEventListener("click", () => { viewer?.plugin.managers.camera.reset(); });
el("story-prev").addEventListener("click", () => { void navigateStory(-1); });
el("story-next").addEventListener("click", () => { void navigateStory(1); });
el("download").addEventListener("click", event => {
  event.stopPropagation();
  if (!scene) return;
  const current = scene;
  const name = current.story ? "molecular-story.mvsj" : `${current.builder?.pdb_id ?? "molecular-scene"}.mvsj`;
  void (async () => {
    if (connected && app.getHostCapabilities()?.downloadFile) {
      const result = await app.downloadFile({ contents: [{ type: "resource", resource: {
        uri: `file:///${encodeURIComponent(name)}`, mimeType: "application/json", text: JSON.stringify(renderedMvs ?? current.mvsj, null, 2),
      } }] });
      if (result.isError) throw new Error("The host could not download the MVSJ file. Check the host's download prompt or try again.");
    } else {
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
      downloadUrl = URL.createObjectURL(new Blob([JSON.stringify(renderedMvs ?? current.mvsj, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = downloadUrl; link.download = name; link.click();
    }
  })().catch(error => status(`Could not save MVSJ: ${error instanceof Error ? error.message : String(error)}`, true));
});

async function saveJson(value: unknown, name: string) {
  if (connected && app.getHostCapabilities()?.downloadFile) {
    const result = await app.downloadFile({ contents: [{ type: "resource", resource: {
      uri: `workspace://pdbe/${name}`, mimeType: "application/json", text: JSON.stringify(value, null, 2),
    } }] });
    if (result.isError) throw new Error("The host could not save the workspace");
    return;
  }
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const link = document.createElement("a"); link.href = downloadUrl; link.download = name; link.click();
}
el("save-workspace").addEventListener("click", () => { if (workspace) { captureView(); void saveJson(workspace, `${workspace.id}.json`).catch(error => status(String(error), true)); } });
el("restore-workspace").addEventListener("change", event => {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  void (async () => {
    if (file.size > 10_000_000) throw new Error("Workspace files must be smaller than 10 MB");
    const saved = validateEnvelope(JSON.parse(await file.text()));
    // Restoration always goes through the same scientific schema and compiler.
    const result = await app.callServerTool({ name: "ebi-pdbe-update_workspace", arguments: { workspace: saved, expected_revision: saved.revision, operations: [] } });
    if (!result.isError) workspace = undefined;
    receive(result);
  })().catch(error => status(String(error), true));
});
el<HTMLSelectElement>("sequence-chain").addEventListener("change", () => {
  sequenceTrackSelection = undefined; sequenceCommittedPositions = [];
  viewer?.plugin.managers.interactivity.lociSelects.deselectAll();
  selectionContext = undefined;
  renderSequencePanel();
  el("sequence-detail").textContent = "Select a sequence position or annotation to inspect it.";
  showSequenceTooltip([]);
  el("selection").textContent = "Select a residue or atom to inspect it.";
  el<HTMLButtonElement>("sequence-focus").disabled = true;
  el<HTMLButtonElement>("sequence-clear").disabled = true;
  workspaceControls();
  void publish({ status: "sequence_chain_changed", chain: sequenceMap?.label_asym_id });
});
el("sequence-manager").addEventListener("change", handleNightingaleChange);
el("sequence-panel").addEventListener("pointerleave", clearSequenceHover);
el("viewer").addEventListener("pointerleave", () => clearSequenceHover());
el<HTMLButtonElement>("sequence-tooltip-close").addEventListener("click", () => showSequenceTooltip([]));
document.addEventListener("click", event => {
  if (!sequenceTooltipPinned) return;
  const path = event.composedPath();
  if (path.includes(el("sequence-tooltip")) || path.includes(el("viewer"))
    || (sequenceTooltipTarget && path.includes(sequenceTooltipTarget))) return;
  showSequenceTooltip([]);
});
el<HTMLButtonElement>("sequence-toggle").addEventListener("click", () => {
  sequenceVisible = !sequenceVisible;
  el<HTMLButtonElement>("sequence-toggle").textContent = sequenceVisible ? "Hide sequence" : "Show sequence";
  el<HTMLButtonElement>("sequence-toggle").setAttribute("aria-pressed", String(sequenceVisible));
  renderSequencePanel();
});
el("sequence-manager").addEventListener("wheel", event => {
  const wheel = event as WheelEvent;
  if (!sequenceMap || wheel.deltaY === 0) return;
  wheel.preventDefault();
  wheel.stopPropagation();
  const unitScale = wheel.deltaMode === WheelEvent.DOM_DELTA_LINE ? 25
    : wheel.deltaMode === WheelEvent.DOM_DELTA_PAGE ? 500 : 1;
  zoomSequence(Math.exp(wheel.deltaY * unitScale * 0.002));
}, { capture: true, passive: false });
el<HTMLButtonElement>("sequence-zoom-in").addEventListener("click", () => zoomSequence(0.5));
el<HTMLButtonElement>("sequence-zoom-out").addEventListener("click", () => zoomSequence(2));
el<HTMLButtonElement>("sequence-zoom-reset").addEventListener("click", () => {
  if (sequenceMap) setSequenceDisplayRange(1, sequenceMap.residues.length);
});
el<HTMLButtonElement>("sequence-show-all").addEventListener("click", () => {
  sequenceTrackSelection = undefined;
  if (sequenceMap) renderDynamicSequenceTracks(sequenceMap);
  void publish({ status: "sequence_tracks_reset", tracks: "all" });
});
el<HTMLButtonElement>("sequence-focus").addEventListener("click", () => {
  if (sequenceCommittedPositions.length) selectSequencePositions(sequenceCommittedPositions, "focus");
});
el<HTMLButtonElement>("sequence-clear").addEventListener("click", () => {
  viewer?.plugin.managers.interactivity.lociSelects.deselectAll();
  sequenceCommittedPositions = [];
  setSequenceHighlight([]); clearSequenceHover();
  selectionContext = undefined;
  el("sequence-detail").textContent = "Select a sequence position or annotation to inspect it.";
  showSequenceTooltip([]);
  el("selection").textContent = "Select a residue or atom to inspect it.";
  el<HTMLButtonElement>("sequence-focus").disabled = true;
  el<HTMLButtonElement>("sequence-clear").disabled = true;
  workspaceControls();
  void publish({ status: "selection_cleared" });
});
el("ask-selection").addEventListener("click", () => {
  if (!selectionContext || !app.getHostCapabilities()?.message) return;
  void app.sendMessage({ role: "user", content: [{ type: "text", text: `Explain this molecular workspace selection using its evidence: ${JSON.stringify(selectionContext)}` }] }).catch(error => status(String(error), true));
});
el("export-comparison").addEventListener("click", () => {
  const comparison = activeWorkspaceScene()?.comparison;
  if (!comparison) return;
  const csv = comparisonCsv(comparison);
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const link = document.createElement("a"); link.href = downloadUrl; link.download = "comparison.csv"; link.click();
});
el<HTMLFormElement>("ligand-explorer-form").addEventListener("submit", event => {
  event.preventDefault();
  void app.callServerTool({ name: "ebi-pdbe-ligand-interactions", arguments: { pdb_id: el<HTMLInputElement>("ligand-pdb-id").value.trim() } }).then(receive).catch(error => status(String(error), true));
});
el<HTMLButtonElement>("restore-ligand-workflow").addEventListener("click", () => {
  const pdbId = el<HTMLInputElement>("ligand-pdb-id").value.trim().toLowerCase();
  try {
    const saved = JSON.parse(localStorage.getItem(`pdbe-ligand-workflow:${pdbId}`) ?? "null") as { data?: LigandData; workspace?: Workspace; filters?: { classification?: string; interactionType?: string; chain?: string; type?: string; maxDistance?: string } } | null;
    if (!saved?.data || !saved.workspace) { status("No complete saved ligand workflow is available for this entry."); return; }
    void app.callServerTool({ name: "ebi-pdbe-update_workspace", arguments: { workspace: saved.workspace, expected_revision: saved.workspace.revision, operations: [] } }).then(result => {
      receive(result);
      renderLigandData(saved.data!);
      const filters = saved.filters;
      if (filters) {
        el<HTMLSelectElement>("contact-classification").value = filters.classification ?? "";
        el<HTMLSelectElement>("contact-interaction-type").value = filters.interactionType ?? "";
        el<HTMLSelectElement>("contact-chain").value = filters.chain ?? "";
        el<HTMLSelectElement>("contact-type").value = filters.type ?? "";
        el<HTMLInputElement>("contact-max-distance").value = filters.maxDistance ?? "";
        renderContactRows();
      }
    }).catch(error => status(String(error), true));
  } catch (error) { status(`Saved ligand workflow could not be restored: ${String(error)}`, true); }
});
el<HTMLSelectElement>("ligand-instance").addEventListener("change", event => {
  const value = (event.currentTarget as HTMLSelectElement).value;
  if (!value) return;
  const [comp_id, auth_asym_id, auth_seq_id, insertion_code, label_asym_id] = JSON.parse(value) as [string, string, string | number, string, string];
  void app.callServerTool({ name: "ebi-pdbe-ligand-interactions", arguments: {
    pdb_id: el<HTMLInputElement>("ligand-pdb-id").value.trim(), comp_id, auth_asym_id, auth_seq_id, insertion_code, label_asym_id,
  } }).then(receive).catch(error => status(String(error), true));
});
for (const id of ["contact-classification", "contact-interaction-type", "contact-chain", "contact-type", "contact-max-distance"]) {
  el(id).addEventListener("input", renderContactRows);
  el(id).addEventListener("change", renderContactRows);
}
el<HTMLButtonElement>("export-contacts").addEventListener("click", () => {
  const records = filteredContacts(); if (!records.length) return;
  if (contactObjectUrl) URL.revokeObjectURL(contactObjectUrl);
  contactObjectUrl = URL.createObjectURL(new Blob([contactCsv(records)], { type: "text/csv" }));
  const link = document.createElement("a"); link.href = contactObjectUrl;
  link.download = `${ligandData?.pdb_id ?? "pdbe"}-${ligandData?.selected?.comp_id ?? "ligand"}-contacts.csv`; link.click();
});
el<HTMLFormElement>("open-form").addEventListener("submit", event => {
  event.preventDefault();
  void app.callServerTool({ name: "ebi-pdbe-open_structure", arguments: { pdb_id: el<HTMLInputElement>("open-pdb").value.trim() } }).then(receive).catch(error => status(String(error), true));
});
el<HTMLFormElement>("compare-form").addEventListener("submit", event => {
  event.preventDefault();
  const args = Object.fromEntries(["reference_pdb_id", "reference_chain_id", "mobile_pdb_id", "mobile_chain_id"].map(id => [id, el<HTMLInputElement>(id).value.trim()]));
  void app.callServerTool({ name: "ebi-pdbe-compare_structures", arguments: args }).then(receive).catch(error => status(String(error), true));
});

app.ontoolinputpartial = () => status("Preparing the molecular scene…");
app.ontoolinput = () => status("Building and validating the molecular scene…");
app.ontoolresult = receive;
app.ontoolcancelled = () => { ++revision; scene = undefined; buttons(false); status("Scene request cancelled."); };
app.onhostcontextchanged = theme;
app.onteardown = async () => {
  disposed = true; ++revision;
  await work;
  viewer?.dispose(); viewer = undefined;
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  return {};
};
void app.connect().then(() => {
  connected = true;
  workspaceControls();
  const context = app.getHostContext();
  if (context) theme(context);
}).catch(() => status("Open this tool in an MCP Apps host to receive a molecular scene.", true));
