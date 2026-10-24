import { App, applyDocumentTheme, applyHostStyleVariables, type McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import type { Viewer } from "molstar-mvs/lib/apps/viewer/app.js";
import { createWorkspaceViewer, displayedStructure } from "./workspace-renderer";
import { residuePositions, attachLayerRefs, coordinateInventory, type SceneNode } from "./workspace-capabilities";
import { validateEnvelope, checkRevision, type Workspace, type WorkspaceOperation } from "./workspace";
import { annotationsAt, detailText } from "./annotations";
import { annotationGroups, isLigandAnnotationLayer, ligandLayerLabel, layerCategory, mergeOptionalScene, type OptionalData } from "./workspace-annotations";
import { comparisonCsv } from "./comparison";
import { StructureElement, StructureProperties } from "molstar-mvs/lib/mol-model/structure.js";
import { OrderedSet } from "molstar-mvs/lib/mol-data/int.js";
import type { UnitIndex } from "molstar-mvs/lib/mol-model/structure/structure/element/util.js";
import "./mvs.css";
import "./workspace.css";

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
  for (const [kind, id] of [["ligands", "show-ligands"], ["annotations", "show-annotations"]] as const) {
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
  renderAnnotationCoverage();
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
  renderResidueBrowser(); workspaceControls();
}

function availableLigands(structure?: import("./workspace").WorkspaceStructure) {
  return structure?.ligands.length ? structure.ligands : inventories.get(`${activeWorkspaceScene()?.id}/${structure?.id}`)?.ligands ?? [];
}
function availableChains(structure?: import("./workspace").WorkspaceStructure) {
  return structure?.chains?.some(chain => chain.residues?.length) ? structure.chains : inventories.get(`${activeWorkspaceScene()?.id}/${structure?.id}`)?.chains ?? [];
}
function renderResidueBrowser() {
  const active = activeWorkspaceScene(), select = el<HTMLSelectElement>("residue-chain");
  const previous = select.value; select.replaceChildren();
  active?.structures.forEach(structure => availableChains(structure).forEach(chain => {
    if (chain.residues?.length) select.add(new Option(`${structure.pdb_id.toUpperCase()} · label ${chain.label_asym_id} / author ${chain.auth_asym_id}`, `${structure.id}/${chain.label_asym_id}`));
  }));
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
  renderResidues();
}
function renderResidues() {
  const [id, chainId] = el<HTMLSelectElement>("residue-chain").value.split("/");
  const structure = activeWorkspaceScene()?.structures.find(s => s.id === id);
  const chain = availableChains(structure).find(c => c.label_asym_id === chainId);
  const query = el<HTMLInputElement>("residue-filter").value.trim().toLowerCase();
  const list = el("residue-list"); list.replaceChildren();
  (chain?.residues ?? []).filter(r => `${r.comp_id} ${r.label_seq_id} ${r.auth_seq_id}${r.insertion_code}`.toLowerCase().includes(query)).slice(0, 100).forEach(residue => {
    const button = document.createElement("button"); button.type = "button";
    button.textContent = `${residue.comp_id} · label ${residue.label_seq_id} / author ${residue.auth_seq_id}${residue.insertion_code}`;
    button.addEventListener("click", () => {
      if (!viewer || !structure || !chain) return;
      const coordinates = displayedStructure(viewer, structure.id);
      const points = coordinates ? residuePositions(coordinates, chain.label_asym_id, residue.label_seq_id) : [];
      if (points.length) viewer.plugin.managers.camera.focusSpheres(points, center => ({ center, radius: 2 }), { minRadius: 8 });
      const evidence = annotationsAt(structure.annotations ?? [], chain.label_asym_id, residue.label_seq_id);
      selectionContext = { structure_id: structure.id, pdb_id: structure.pdb_id, ...residue,
        label_asym_id: chain.label_asym_id, auth_asym_id: chain.auth_asym_id, annotations: evidence };
      el("selection").textContent = `${button.textContent}${points.length ? "" : " · coordinates unavailable"}${evidence.length ? " · " + evidence.map(e => `${e.feature.source}: ${e.feature.name}`).join("; ") : ""}`;
      void publish({ status: "selection", selection: selectionContext });
    });
    list.append(button);
  });
}
async function mutate(operations: WorkspaceOperation[], prepare?: () => Promise<WorkspaceOperation[]>) {
  if (!workspace || updating) return;
  updating = true; workspaceControls(); status("Validating workspace update…");
  try {
    if (prepare) operations = await prepare();
    captureView();
    const result = await app.callServerTool({ name: "ebi-pdbe-update_workspace", arguments: { workspace, expected_revision: workspace.revision, operations } });
    receive(result);
    if (result.isError) { renderWorkspaceControls(); return; }
    await work;
  } catch (error) { status(String(error), true); renderWorkspaceControls(); }
  finally { updating = false; workspaceControls(); }
}

function renderAnnotationCoverage() {
  const container = el("annotation-coverage"), active = activeWorkspaceScene(); container.replaceChildren();
  if (!active) return;
  const groups = annotationGroups(active);
  if (groups.length) {
    const heading = document.createElement("h3"); heading.textContent = "Residue annotations"; container.append(heading);
    const hint = document.createElement("p"); hint.className = "hint";
    hint.textContent = "Coverage is the unique annotated residues / listed residues in this chain. It is not a confidence score. Expand an annotation group to inspect supplied values and provenance."; container.append(hint);
  }
  for (const group of groups) {
    const details = document.createElement("details"), summary = document.createElement("summary");
    const coverage = group.percent === null ? "coverage unavailable" : `${Number(group.percent.toFixed(1))}% (${group.covered}/${group.total} residues)`;
    summary.textContent = `${group.pdbId.toUpperCase()} · ${group.provider} · chain ${group.chainId} · ${coverage}`;
    details.append(summary);
    const layers = active.layers.filter(layer => group.layerIds.includes(layer.id));
    if (layers.length) {
      const label = document.createElement("label"), toggle = document.createElement("input"); toggle.type = "checkbox";
      toggle.checked = layers.some(layer => layer.visible); toggle.indeterminate = toggle.checked && layers.some(layer => !layer.visible);
      toggle.addEventListener("change", () => {
        const scene = structuredClone(activeWorkspaceScene()!);
        for (const layer of scene.layers) if (group.layerIds.includes(layer.id)) layer.visible = toggle.checked;
        void mutate([{ op: "upsert_scene", scene_id: scene.id, target_id: scene.id, scene }]);
      });
      label.append(toggle, document.createTextNode("Show annotation highlights")); details.append(label);
    }
    // Build detailed evidence only on expansion. Raw values remain in workspace/context.
    details.addEventListener("toggle", () => {
      if (!details.open || details.dataset.rendered) return;
      details.dataset.rendered = "true";
      if (group.percent === 100) {
        const hint = document.createElement("p"); hint.className = "hint";
        hint.textContent = "This annotation group covers every listed residue. Inspect its raw values to distinguish residues."; details.append(hint);
      }
      const limit = 200;
      for (const feature of group.features.slice(0, limit)) {
        const record = document.createElement("details"), name = document.createElement("summary");
        name.textContent = [...new Set([feature.name, feature.accession, feature.description].filter(value => value && value !== group.provider))].join(" · ") || "Source annotation";
        record.append(name);
        const values = document.createElement("pre");
        values.textContent = feature.segments.filter(segment => segment.label_asym_id === group.chainId)
          .map(segment => `Residues ${segment.start}–${segment.end}${Object.keys(segment.details ?? {}).length ? " · " + detailText(segment.details) : ""}`).join("\n"); record.append(values);
        if (/^https?:\/\//i.test(feature.source_url)) {
          const link = document.createElement("a"); link.href = feature.source_url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = "Source evidence"; record.append(link);
        }
        details.append(record);
      }
      if (group.features.length > limit) {
        const hint = document.createElement("p"); hint.className = "hint";
        hint.textContent = `Showing ${limit} of ${group.features.length} records. All records and values are retained in saved workspace JSON and residue inspection.`; details.append(hint);
      }
    });
    container.append(details);
  }
}
async function toggleOptional(kind: OptionalData, visible: boolean) {
  if (!workspace || !activeWorkspaceScene()) return;
  const originalId = workspace.id, originalRevision = workspace.revision;
  const base = structuredClone(activeWorkspaceScene()!);
  await mutate([], async () => {
    status(visible ? `Loading optional ${kind}…` : `Hiding ${kind}…`);
    const pending = visible ? base.structures.filter(structure => structure.data_status?.[kind] !== "loaded") : [];
    const fetched = await Promise.all(pending.map(async structure => {
      const result = await app.callServerTool({ name: "ebi-pdbe-open_structure", arguments: {
        pdb_id: structure.pdb_id, include_annotations: kind === "annotations", include_ligands: kind === "ligands",
      } });
      if (result.isError) throw new Error(result.content?.filter(item => item.type === "text").map(item => item.text).join("\n") || `Could not load ${kind}`);
      const supplied = result._meta?.workspace as Workspace | undefined;
      if (!supplied?.scenes?.[0]) throw new Error(`The server did not return optional ${kind} workspace data`);
      return { structureId: structure.id, scene: supplied.scenes[0] };
    }));
    if (!workspace || workspace.id !== originalId || workspace.revision !== originalRevision
      || JSON.stringify(activeWorkspaceScene()) !== JSON.stringify(base)) throw new Error("Workspace changed while fetching data. Please retry with the current view.");
    const updated = mergeOptionalScene(base, fetched, kind, visible);
    return [{ op: "upsert_scene", scene_id: updated.id, target_id: updated.id, scene: updated }];
  });
}
el<HTMLInputElement>("show-ligands").addEventListener("change", event => { void toggleOptional("ligands", (event.target as HTMLInputElement).checked); });
el<HTMLInputElement>("show-annotations").addEventListener("change", event => { void toggleOptional("annotations", (event.target as HTMLInputElement).checked); });

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
      selectionContext = { ...selection, annotations: selectedStructure ? annotationsAt(selectedStructure.annotations ?? [], selection.label_asym_id, selection.label_seq_id) : [] };
      el("selection").textContent = `${selection.comp_id} · author chain ${selection.auth_asym_id} residue ${selection.auth_seq_id}${selection.insertion_code} · label chain ${selection.label_asym_id}${selection.label_seq_id === null ? "" : ` residue ${selection.label_seq_id}`}`;
      void publish({ status: "selection", selection }).catch(error => status(String(error), true));
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
el("download").addEventListener("click", () => {
  if (!scene) return;
  const current = scene;
  const name = current.story ? "molecular-story.mvsj" : `${current.builder?.pdb_id ?? "molecular-scene"}.mvsj`;
  void (async () => {
    if (connected && app.getHostCapabilities()?.downloadFile) {
      const result = await app.downloadFile({ contents: [{ type: "resource", resource: {
        uri: `mvs://pdbe/${name}`, mimeType: "application/json", text: JSON.stringify(renderedMvs ?? current.mvsj, null, 2),
      } }] });
      if (result.isError) throw new Error("The host could not save the MVSJ file");
    } else {
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
      downloadUrl = URL.createObjectURL(new Blob([JSON.stringify(renderedMvs ?? current.mvsj, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = downloadUrl; link.download = name; link.click();
    }
  })().catch(error => status(String(error), true));
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
el("residue-chain").addEventListener("change", renderResidues);
el("residue-filter").addEventListener("input", renderResidues);
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
