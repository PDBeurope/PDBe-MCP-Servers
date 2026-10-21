import { App, applyDocumentTheme, applyHostStyleVariables, type McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import "pdbe-molstar/build/pdbe-molstar-plugin.js";
import type { PDBeMolstarPlugin } from "pdbe-molstar/lib/viewer";
import type { QueryParam } from "pdbe-molstar/lib/helpers";
import { annotationColor, annotationTooltips, annotationsAt, buildVisualData, detailText, segmentQuery, type Annotation } from "./annotations";
import "pdbe-molstar/build/pdbe-molstar-light.css";
import "./style.css";

declare global {
  interface Window { PDBeMolstarPlugin: new () => PDBeMolstarPlugin }
}

interface Residue {
  label_seq_id: number | null;
  auth_seq_id: number | null;
  insertion_code: string;
  comp_id: string;
  observed_ratio?: number | null;
}
interface Chain {
  entity_id: string;
  label_asym_id: string;
  auth_asym_id: string;
  name: string;
  molecule_type: string;
  residues: Residue[];
}
interface Ligand extends Residue {
  entity_id: string;
  label_asym_id: string;
  auth_asym_id: string;
  name: string;
}
interface StructureData {
  pdb_id: string;
  title: string;
  experimental_methods: string[];
  assembly_id: string | null;
  initial_chain_id: string | null;
  model_index: number;
  chains: Chain[];
  ligands: Ligand[];
  entry_url: string;
  coordinate_url: string;
  sources: string[];
  retrieved_at: string;
  warnings: string[];
  annotations: Annotation[];
}
interface Selection extends Residue {
  pdb_id: string;
  assembly_id: string | null;
  model_id: number | null;
  instance_id?: string;
  label_asym_id: string;
  auth_asym_id: string;
  entity_id: string;
  atom_ids?: string[];
}
interface ViewerEvent {
  label_asym_id?: string;
  auth_asym_id?: string;
  entity_id?: string;
  seq_id?: number;
  auth_seq_id?: number;
  ins_code?: string;
  comp_id?: string;
  model?: number;
  instance?: string;
  atom_id?: string[];
}
interface ToolResult {
  isError?: boolean;
  content?: { type: string; text?: string }[];
  structuredContent?: unknown;
  _meta?: Record<string, unknown>;
}

function el<T extends HTMLElement = HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing element ${id}`);
  return element as T;
}
function button(text: string, action: () => Promise<void>): HTMLButtonElement {
  const item = document.createElement("button");
  item.type = "button";
  item.textContent = text;
  item.addEventListener("click", () => { void action().catch(showError); });
  return item;
}
function status(message: string, error = false): void {
  el("status").textContent = message;
  el("status").classList.toggle("error", error);
}
function showError(error: unknown): void {
  status(error instanceof Error ? error.message : String(error), true);
}

function publishSelection(item: Selection | null): void {
  if (connected && app.getHostCapabilities()?.updateModelContext) {
    const evidence = item ? annotationsAt(structure?.annotations ?? [], item.label_asym_id, item.label_seq_id)
      .map(({ feature, segment }) => ({ source: feature.source, accession: feature.accession, name: feature.name, details: segment.details, source_url: feature.source_url })) : [];
    void app.updateModelContext({ structuredContent: { pdbe_selection: item, pdbe_annotations: evidence } }).catch(showError);
  }
}

const app = new App({ name: "PDBe Structure Explorer", version: "0.1.0" });
let viewer: PDBeMolstarPlugin | undefined;
let structure: StructureData | undefined;
let selection: Selection | undefined;
let modelId: number | null = null;
let ready = false;
let loading = false;
let requesting = false;
let connected = false;
let disposed = false;
let revision = 0;
let work = Promise.resolve();
let visualWork = Promise.resolve();
const hiddenChains = new Set<string>();

function setControls(): void {
  el<HTMLButtonElement>("open").disabled = !connected || loading || requesting;
  for (const id of ["reset", "clear"]) el<HTMLButtonElement>(id).disabled = !ready;
  el<HTMLButtonElement>("focus").disabled = !ready || !selection;
  el<HTMLButtonElement>("ask").disabled = !ready || !selection || !connected;
  el<HTMLSelectElement>("residue-chain").disabled = !ready;
  el<HTMLInputElement>("residue-filter").disabled = !ready;
  el<HTMLSelectElement>("annotation-layer").disabled = !ready;
  el<HTMLInputElement>("annotation-tooltips").disabled = !ready;
  el("evidence").classList.toggle("loading", !ready);
}

function theme(ctx: McpUiHostContext): void {
  if (ctx.theme) applyDocumentTheme(ctx.theme);
  if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
  if (ctx.safeAreaInsets) {
    const { top, right, bottom, left } = ctx.safeAreaInsets;
    document.body.style.padding = `${top}px ${right}px ${bottom}px ${left}px`;
  }
}

function query(item: Selection): QueryParam {
  return {
    label_asym_id: item.label_asym_id,
    // Author numbering plus insertion code also handles non-polymer residues,
    // whose label_seq_id is undefined in mmCIF.
    ...(item.auth_seq_id !== null
      ? { auth_seq_id: item.auth_seq_id, pdbx_PDB_ins_code: item.insertion_code }
      : item.label_seq_id !== null ? { label_seq_id: item.label_seq_id } : {}),
    ...(item.instance_id ? { instance_id: item.instance_id } : {}),
  };
}

function markSelectedRows(): void {
  for (const row of document.querySelectorAll<HTMLButtonElement>("[data-residue-key]")) {
    const selected = !!selection && row.dataset.residueKey === residueKey(selection);
    row.classList.toggle("selected", selected);
    row.setAttribute("aria-pressed", String(selected));
  }
}
function residueKey(item: Residue & { label_asym_id: string }): string {
  return JSON.stringify([item.label_asym_id, item.auth_seq_id, item.insertion_code, item.comp_id]);
}

function showSelection(item: Selection): void {
  selection = item;
  el("selection-summary").textContent = `${item.comp_id} · author chain ${item.auth_asym_id} · residue ${item.auth_seq_id ?? "?"}${item.insertion_code}`;
  const details = el("selection-details");
  details.replaceChildren();
  const fields: [string, string][] = [
    ["PDB entry", item.pdb_id.toUpperCase()],
    ["View", item.assembly_id ? `Assembly ${item.assembly_id}` : "Asymmetric unit"],
    ["Model", String(item.model_id ?? "First coordinate model")],
    ["Label chain", item.label_asym_id],
    ["Label residue", String(item.label_seq_id ?? "Not assigned")],
    ["Insertion code", item.insertion_code || "None"],
  ];
  if (item.instance_id) fields.push(["Symmetry instance", item.instance_id]);
  if (item.atom_ids?.length) fields.push(["Atoms", item.atom_ids.join(", ")]);
  for (const [name, value] of fields) {
    const term = document.createElement("dt");
    term.textContent = name;
    const detail = document.createElement("dd");
    detail.textContent = value;
    details.append(term, detail);
  }
  const chooser = el<HTMLSelectElement>("residue-chain");
  if (Array.from(chooser.options).some(o => o.value === item.label_asym_id)) {
    chooser.value = item.label_asym_id;
    el<HTMLInputElement>("residue-filter").value = String(item.auth_seq_id ?? item.comp_id);
    renderResidues();
  }
  markSelectedRows();
  renderSelectionAnnotations();
  setControls();
  publishSelection(item);
}

async function selectResidue(item: Residue, chain: Pick<Chain, "entity_id" | "label_asym_id" | "auth_asym_id">): Promise<void> {
  if (!ready || !viewer || !structure) return;
  if (item.observed_ratio === 0) {
    status("This residue has no observed coordinates to highlight.");
    return;
  }
  const next: Selection = {
    ...item, ...chain, pdb_id: structure.pdb_id,
    assembly_id: structure.assembly_id, model_id: modelId,
  };
  const loci = viewer.getLociForParams([query(next)]);
  if (loci.kind !== "element-loci" || loci.elements.length === 0) {
    status("This residue is absent from the displayed coordinates or assembly.");
    return;
  }
  if (hiddenChains.delete(chain.label_asym_id)) await applyVisibility();
  showSelection(next);
  await applyVisuals(true);
  status("Selection highlighted. Drag to rotate; scroll to zoom.");
}

async function applyVisibility(): Promise<void> {
  if (!viewer || !structure) return;
  await applyVisuals();
  for (const input of document.querySelectorAll<HTMLInputElement>("[data-chain-visibility]")) {
    input.checked = !hiddenChains.has(input.dataset.chainVisibility!);
  }
}

function activeAnnotations(): Annotation[] {
  const layer = el<HTMLSelectElement>("annotation-layer").value;
  return (structure?.annotations ?? []).filter(feature => `${feature.kind}:${feature.source}` === layer);
}

function applyVisuals(focus = false): Promise<void> {
  if (!viewer || !structure || !ready) return Promise.resolve();
  const target = viewer;
  const currentRevision = revision;
  const data = [
    ...buildVisualData(activeAnnotations(), structure.chains.map(c => c.label_asym_id), hiddenChains),
    ...buildVisualData([], [], hiddenChains, selection ? query(selection) : undefined, focus),
  ];
  visualWork = visualWork.catch(() => {}).then(async () => {
    if (viewer !== target || currentRevision !== revision || !ready) return;
    // The viewer supports color:null to preserve base colours, although its
    // published declaration omits null from the colour type.
    await target.visual.select({ data: data as Parameters<PDBeMolstarPlugin["visual"]["select"]>[0]["data"] });
  });
  return visualWork;
}

async function applyAnnotationTooltips(): Promise<void> {
  if (!viewer || !ready) return;
  await viewer.visual.tooltips({ data: el<HTMLInputElement>("annotation-tooltips").checked
    ? annotationTooltips(structure?.annotations ?? []) : [] });
}

function renderAnnotationFeatures(): void {
  const list = el("annotation-features");
  list.replaceChildren();
  const features = activeAnnotations();
  for (const [index, feature] of features.entries()) {
    const ranges = feature.segments.map(s => `${s.label_asym_id}:${s.start}–${s.end}`).join(", ");
    const item = button(`${feature.accession} · ${feature.name}${feature.description ? ` · ${feature.description}` : ""}\n${ranges}`, async () => {
      if (!ready) return;
      let visibilityChanged = false;
      for (const segment of feature.segments) visibilityChanged = hiddenChains.delete(segment.label_asym_id) || visibilityChanged;
      if (visibilityChanged) await applyVisibility();
      await viewer?.visual.focus(feature.segments.map(segmentQuery));
      status(`${feature.source} · ${feature.name} · ${feature.segments.length} mapped segments. Source: ${feature.source_url}`);
    });
    item.className = "annotation-feature";
    item.style.borderLeftColor = annotationColor(index);
    list.append(item);
  }
  if (!features.length) list.textContent = structure?.annotations.length
    ? "Choose an annotation source to view and focus its features."
    : "No annotations could be mapped for this entry. Check any warnings above.";
}

function renderAnnotationControls(): void {
  const chooser = el<HTMLSelectElement>("annotation-layer");
  chooser.replaceChildren(new Option("Original structure colours", ""));
  const layers = new Map<string, string>();
  for (const feature of structure?.annotations ?? []) layers.set(`${feature.kind}:${feature.source}`, `${feature.kind.replaceAll("_", " ")} · ${feature.source}`);
  for (const [key, label] of layers) chooser.append(new Option(label, key));
  chooser.value = [...layers.keys()].find(key => key.startsWith("domains:")) ?? "";
  renderAnnotationFeatures();
  renderSelectionAnnotations();
}

function renderSelectionAnnotations(): void {
  const list = el("selection-annotations");
  list.replaceChildren();
  if (!selection) {
    list.textContent = "Select a residue to inspect its evidence.";
    return;
  }
  const matches = annotationsAt(structure?.annotations ?? [], selection.label_asym_id, selection.label_seq_id);
  for (const { feature, segment } of matches) {
    const row = document.createElement("div");
    row.className = "annotation-evidence";
    const title = document.createElement("strong");
    title.textContent = `${feature.source} · ${feature.accession} · ${feature.name}`;
    const details = document.createElement("p");
    details.textContent = detailText(segment.details);
    row.append(title, details, button("Evidence source", async () => { await app.openLink({ url: feature.source_url }); }));
    list.append(row);
  }
  if (!matches.length) list.textContent = "No mapped annotations for this residue. This does not establish absence of function.";
}

function renderChains(): void {
  const list = el("chains");
  const chooser = el<HTMLSelectElement>("residue-chain");
  list.replaceChildren();
  chooser.replaceChildren();
  for (const chain of structure?.chains ?? []) {
    const row = document.createElement("div");
    row.className = "chain-row";
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.checked = true;
    toggle.dataset.chainVisibility = chain.label_asym_id;
    toggle.setAttribute("aria-label", `Show label chain ${chain.label_asym_id}`);
    toggle.addEventListener("change", () => {
      if (!ready) return;
      if (toggle.checked) hiddenChains.delete(chain.label_asym_id);
      else hiddenChains.add(chain.label_asym_id);
      void applyVisibility().catch(showError);
    });
    const focus = button(`${chain.auth_asym_id} / ${chain.label_asym_id}`, async () => {
      if (!ready) return;
      if (hiddenChains.delete(chain.label_asym_id)) await applyVisibility();
      await viewer?.visual.focus([{ label_asym_id: chain.label_asym_id }]);
      chooser.value = chain.label_asym_id;
      el<HTMLInputElement>("residue-filter").value = "";
      renderResidues();
    });
    focus.title = chain.name || chain.molecule_type;
    const name = document.createElement("span");
    name.textContent = chain.name || chain.molecule_type;
    row.append(toggle, focus, name);
    list.append(row);
    if (chain.molecule_type !== "water") {
      const option = document.createElement("option");
      option.value = chain.label_asym_id;
      option.textContent = `${chain.auth_asym_id} / ${chain.label_asym_id} · ${chain.name}`;
      chooser.append(option);
    }
  }
  renderResidues();
}

function renderResidues(): void {
  const list = el("residues");
  list.replaceChildren();
  const chain = structure?.chains.find(c => c.label_asym_id === el<HTMLSelectElement>("residue-chain").value);
  if (!chain) return;
  const filter = el<HTMLInputElement>("residue-filter").value.toLowerCase().trim();
  const residues = chain.residues.filter(r => `${r.comp_id} ${r.auth_seq_id}${r.insertion_code} label ${r.label_seq_id}`.toLowerCase().includes(filter));
  for (const residue of residues.slice(0, 200)) {
    const item = button(`${residue.comp_id} ${residue.auth_seq_id ?? "?"}${residue.insertion_code}${residue.observed_ratio === 0 ? " · unobserved" : ""}`, async () => {
      // Use normalized ligand identifiers for non-polymer residues.
      const ligand = structure?.ligands.find(l => residueKey(l) === residueKey({ ...residue, label_asym_id: chain.label_asym_id }));
      await selectResidue(ligand ?? residue, chain);
    });
    item.dataset.residueKey = residueKey({ ...residue, label_asym_id: chain.label_asym_id });
    item.setAttribute("role", "listitem");
    list.append(item);
  }
  if (!residues.length || residues.length > 200) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = residues.length ? `Showing 200 of ${residues.length}. Type to narrow the list.` : "No matching residue records. You can still select residues in 3D.";
    list.append(hint);
  }
  markSelectedRows();
}

function renderLigands(): void {
  const list = el("ligands");
  list.replaceChildren();
  for (const ligand of structure?.ligands ?? []) {
    const item = button(`${ligand.comp_id} · ${ligand.auth_asym_id}:${ligand.auth_seq_id}${ligand.insertion_code} (label ${ligand.label_asym_id})`, async () => {
      await selectResidue(ligand, ligand);
    });
    item.className = "ligand";
    item.title = ligand.name;
    item.dataset.residueKey = residueKey(ligand);
    list.append(item);
  }
  if (!structure?.ligands.length) list.textContent = "No ligand instances reported by PDBe.";
}

function fromViewer(event: Event): void {
  if (!ready || !structure) return;
  const data = (event as Event & { eventData?: ViewerEvent }).eventData;
  if (!data?.label_asym_id || !data.comp_id) return;
  const chain = structure.chains.find(c => c.label_asym_id === data.label_asym_id);
  const ligand = structure.ligands.find(l => l.label_asym_id === data.label_asym_id && l.auth_seq_id === data.auth_seq_id && l.insertion_code === (data.ins_code || ""));
  showSelection({
    pdb_id: structure.pdb_id, assembly_id: structure.assembly_id,
    model_id: data.model ?? modelId, instance_id: data.instance,
    entity_id: data.entity_id ?? chain?.entity_id ?? "",
    label_asym_id: data.label_asym_id, auth_asym_id: data.auth_asym_id ?? chain?.auth_asym_id ?? "",
    label_seq_id: ligand ? null : data.seq_id && data.seq_id > 0 ? data.seq_id : null,
    auth_seq_id: data.auth_seq_id ?? null, insertion_code: data.ins_code || "",
    comp_id: data.comp_id, atom_ids: data.atom_id,
  });
  // The viewer already applies focus on click; coloring the whole residue makes
  // the selection persist while the evidence panel and lists stay synchronized.
  void applyVisuals().catch(showError);
}

async function loadStructure(data: StructureData, loadRevision: number): Promise<void> {
  if (disposed || loadRevision !== revision) return;
  loading = true;
  ready = false;
  selection = undefined;
  publishSelection(null);
  setControls();
  status(`Loading ${data.pdb_id.toUpperCase()} coordinates…`);
  await visualWork.catch(showError);
  viewer?.plugin?.dispose();
  el("viewer").replaceChildren();
  if (typeof window.PDBeMolstarPlugin !== "function") {
    throw new Error("PDBe Mol* could not initialize. Rebuild the Structure Explorer UI and reopen the app.");
  }
  viewer = new window.PDBeMolstarPlugin();
  structure = data;
  hiddenChains.clear();
  el<HTMLInputElement>("pdb-id").value = data.pdb_id;
  el("entry").hidden = false;
  el("entry-title").textContent = `${data.pdb_id.toUpperCase()} · ${data.title}`;
  el("entry-meta").textContent = data.experimental_methods.join(" · ");
  el("warnings").textContent = data.warnings.join(" ");
  el("selection-summary").textContent = "Select a residue or ligand in the viewer or the lists below.";
  el("selection-details").replaceChildren();
  el<HTMLInputElement>("residue-filter").value = "";
  renderChains();
  renderLigands();
  // render() initializes the plugin but starts coordinate loading in the
  // background. Wait for its loadComplete event before enabling interactions.
  let finishLoading!: (ok: boolean) => void;
  const loadComplete = new Promise<boolean>(resolve => { finishLoading = resolve; });
  const subscription = viewer.events.loadComplete.subscribe(finishLoading);
  const timeout = window.setTimeout(() => finishLoading(false), 60_000);
  let loaded = false;
  try {
    await viewer.render(el("viewer"), {
      customData: { url: data.coordinate_url, format: "cif", binary: true },
      assemblyId: data.assembly_id ?? undefined,
      bgColor: { r: 247, g: 250, b: 252 },
      hideControls: true, hideCanvasControls: ["expand", "screenshot"],
      landscape: true, loadMaps: false, pdbeLink: false,
      selectInteraction: true, subscribeEvents: false,
    });
    loaded = await loadComplete;
  } finally { subscription.unsubscribe(); window.clearTimeout(timeout); }
  if (disposed || loadRevision !== revision) return;
  if (!loaded) throw new Error("Could not load coordinates. Check network access to www.ebi.ac.uk and WebGL support, then open the structure again.");
  const loadedModel = viewer.getStructure(1)?.cell.obj?.data.models[0];
  modelId = loadedModel?.modelNum ?? null;
  ready = true;
  renderAnnotationControls();
  try {
    await applyAnnotationTooltips();
    await applyVisuals();
  } catch (error) {
    el("warnings").textContent += ` Annotation rendering is unavailable: ${error instanceof Error ? error.message : String(error)}`;
  }
  const description = `${data.assembly_id ? `Biological assembly ${data.assembly_id}` : "Deposited asymmetric unit"} · model ${modelId ?? "first"}. Chain and ligand lists describe the deposited entry; assembly views can omit chains or show symmetry copies. List selections apply to all copies of a chain; 3D clicks preserve the selected instance.`;
  el("view-description").textContent = description;
  el("provenance").hidden = false;
  el("sources").replaceChildren();
  for (const url of [...data.sources, data.coordinate_url]) {
    const item = document.createElement("li");
    const label = url === data.coordinate_url ? "Coordinates (BinaryCIF)" : new URL(url).pathname.split("/entry/").at(-1)?.replaceAll("/", " · ") ?? "PDBe source";
    item.append(button(label, async () => { await app.openLink({ url }); }));
    el("sources").append(item);
  }
  el("retrieved").textContent = `Retrieved ${new Date(data.retrieved_at).toLocaleString()}`;
  setControls();
  if (data.initial_chain_id) {
    await viewer.visual.focus([{ label_asym_id: data.initial_chain_id }]);
    el<HTMLSelectElement>("residue-chain").value = data.initial_chain_id;
    renderResidues();
  }
  status(`${data.pdb_id.toUpperCase()} ready · drag to rotate, scroll to zoom, click a residue to inspect.`);
}

function receiveResult(result: ToolResult): Promise<void> {
  if (result.isError) {
    showError(result.content?.find(c => c.type === "text")?.text ?? "Could not open the structure.");
    return Promise.resolve();
  }
  const raw = result._meta?.structure ?? result.structuredContent;
  if (!raw || typeof raw !== "object" || !("pdb_id" in raw) || !("chains" in raw) || !Array.isArray(raw.chains)) {
    showError("The server did not return Structure Explorer data.");
    return Promise.resolve();
  }
  const data = raw as StructureData;
  data.annotations ??= [];
  data.chains = data.chains.map(c => ({ ...c, residues: c.residues ?? [] }));
  const loadRevision = ++revision;
  work = work.then(() => loadStructure(data, loadRevision)).catch(error => {
    if (loadRevision === revision) {
      ready = false;
      viewer?.plugin?.dispose();
      viewer = undefined;
      setControls();
      showError(error);
    }
  }).finally(() => { loading = false; setControls(); });
  return work;
}

el("open-form").addEventListener("submit", event => {
  event.preventDefault();
  const pdbId = el<HTMLInputElement>("pdb-id").value.trim().toLowerCase();
  requesting = true;
  setControls();
  status(`Retrieving ${pdbId.toUpperCase()} metadata…`);
  void app.callServerTool({ name: "ebi-pdbe-open_structure", arguments: { pdb_id: pdbId } })
    .then(receiveResult).catch(showError).finally(() => { requesting = false; setControls(); });
});
el("reset").addEventListener("click", () => { void viewer?.visual.reset({ camera: true }).catch(showError); });
el("focus").addEventListener("click", () => {
  if (selection) void viewer?.visual.focus([query(selection)]).catch(showError);
});
el("clear").addEventListener("click", () => {
  selection = undefined;
  el("selection-summary").textContent = "Select a residue or ligand in the viewer or the lists below.";
  el("selection-details").replaceChildren();
  renderSelectionAnnotations();
  markSelectedRows();
  setControls();
  void applyVisuals().catch(showError);
  publishSelection(null);
});
el("ask").addEventListener("click", () => {
  if (!selection) return;
  void app.sendMessage({ role: "user", content: [{ type: "text", text: `Explain the available structural evidence for this selection: ${JSON.stringify(selection)}. Distinguish supported annotations from inference.` }] }).catch(showError);
});
el("source").addEventListener("click", () => {
  if (structure) void app.openLink({ url: structure.entry_url }).catch(showError);
});
el("residue-chain").addEventListener("change", () => { el<HTMLInputElement>("residue-filter").value = ""; renderResidues(); });
el("residue-filter").addEventListener("input", renderResidues);
el("annotation-layer").addEventListener("change", () => { renderAnnotationFeatures(); void applyVisuals().catch(showError); });
el("annotation-tooltips").addEventListener("change", () => { void applyAnnotationTooltips().catch(showError); });
el("viewer").addEventListener("PDB.molstar.click", fromViewer);

// All lifecycle handlers must be registered before the host handshake.
app.ontoolinput = params => { status(`Preparing ${String(params.arguments?.pdb_id ?? "structure").toUpperCase()}…`); };
app.ontoolresult = result => { void receiveResult(result); };
app.ontoolcancelled = () => { ++revision; status("Structure request cancelled. Open a structure to continue."); };
app.onhostcontextchanged = theme;
app.onerror = showError;
app.onteardown = async () => {
  disposed = true;
  ++revision;
  await work;
  await visualWork.catch(() => {});
  viewer?.plugin?.dispose();
  return {};
};
void app.connect().then(() => {
  connected = true;
  const context = app.getHostContext();
  if (context) theme(context);
  setControls();
  if (!structure) status("Connected. Open a PDB structure to begin.");
}).catch(() => {
  status("Open this tool in an MCP Apps client to connect the viewer to PDBe.", true);
});
