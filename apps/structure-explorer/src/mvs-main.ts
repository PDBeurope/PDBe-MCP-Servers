import { App, applyDocumentTheme, applyHostStyleVariables, type McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import { Viewer } from "molstar-mvs/lib/apps/viewer/app.js";
import { StructureElement, StructureProperties } from "molstar-mvs/lib/mol-model/structure.js";
import { OrderedSet } from "molstar-mvs/lib/mol-data/int.js";
import "./mvs.css";

interface LegendItem {
  label: string;
  representation: string;
  colors?: string[];
}

interface SceneResult {
  version: 1;
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

const app = new App({ name: "PDBe Custom Molecular View", version: "0.1.0" });
let viewer: Viewer | undefined;
let scene: SceneResult | undefined;
let connected = false;
let disposed = false;
let revision = 0;
let work = Promise.resolve();
let downloadUrl: string | undefined;

function buttons(ready: boolean): void {
  el<HTMLButtonElement>("reset").disabled = !ready;
  el<HTMLButtonElement>("download").disabled = !ready;
}

function currentScene() {
  return scene?.scenes?.find(item => item.id === viewer?.plugin.managers.snapshot.current?.key) ?? scene?.scenes?.[0];
}

function showSceneDetails(): void {
  const active = currentScene();
  const legend = active?.legend ?? scene?.legend ?? [];
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

async function publish(data: Record<string, unknown>): Promise<void> {
  if (connected && !disposed && app.getHostCapabilities()?.updateModelContext) {
    try {
      await app.updateModelContext({ structuredContent: { pdbe_mvs: data } });
    } catch (error) {
      // Host context is optional; its failure must not misreport a rendered scene.
      console.warn("Could not update the host's molecular scene context", error);
    }
  }
}

async function load(result: SceneResult, token: number): Promise<void> {
  if (disposed || token !== revision) return;
  scene = result;
  buttons(false);
  status("Loading coordinates and constructing the molecular view…");
  el("title").textContent = result.story?.title ?? result.builder?.title ?? "Molecular view";
  el("description").textContent = result.story?.description ?? result.builder?.description ?? "";
  el("warnings").textContent = result.warnings.join(" ");
  el("selection").textContent = "Select a residue or atom to inspect it.";
  showSceneDetails();
  try {
    viewer?.dispose();
    viewer = undefined;
    el("viewer").replaceChildren();
    const created = await Viewer.create(el("viewer"), {
      layoutIsExpanded: false, layoutShowControls: false, layoutShowSequence: false,
      layoutShowLog: false, layoutShowLeftPanel: false, viewportShowExpand: false,
      viewportShowToggleFullscreen: false, volumeStreamingDisabled: true,
      extensions: ["mvs"], pdbProvider: "pdbe",
    });
    if (disposed || token !== revision) { created.dispose(); return; }
    viewer = created;
    await created.loadMvsData(JSON.stringify(result.mvsj), "mvsj", { sanityChecks: true });
    if (disposed || token !== revision) return;
    const structures = created.plugin.managers.structure.hierarchy.current.structures;
    const atomCount = structures.reduce((count, s) => count + (s.cell.obj?.data.elementCount ?? 0), 0);
    const components = structures.flatMap(s => s.components);
    const empty = components.filter(c => !c.cell.obj?.data.elementCount).length;
    const hasVisibleAtoms = components.some(c => (c.cell.obj?.data.elementCount ?? 0) > 0);
    const message = atomCount === 0 ? "The coordinates loaded, but no atoms are available in this structure."
      : empty ? `Scene loaded. ${empty} selection(s) contain no atoms; check chain IDs and residue numbering.`
      : "Molecular view ready. Rotate, zoom, or select a residue to inspect it.";
    status(message, atomCount === 0 || empty > 0);
    await publish({ status: hasVisibleAtoms ? "loaded" : "empty", pdb_id: currentScene()?.builder.pdb_id ?? result.builder?.pdb_id, atom_count: atomCount, empty_components: empty });
    created.subscribe(created.plugin.managers.snapshot.events.changed, () => {
      if (disposed || token !== revision) return;
      showSceneDetails();
      const active = currentScene();
      if (active) void publish({ status: "story_scene", scene_id: active.id, pdb_id: active.builder.pdb_id, playing: created.plugin.managers.snapshot.state.isPlaying });
    });
    showSceneDetails();
    created.subscribe(created.plugin.behaviors.interaction.click, event => {
      if (!StructureElement.Loci.is(event.current.loci) || StructureElement.Loci.isEmpty(event.current.loci)) return;
      const loci = event.current.loci;
      const first = loci.elements[0];
      const location = StructureElement.Location.create(loci.structure, first.unit, first.unit.elements[OrderedSet.getAt(first.indices, 0)]);
      const p = StructureProperties;
      const selection = {
        pdb_id: currentScene()?.builder.pdb_id ?? result.builder?.pdb_id,
        label_asym_id: p.chain.label_asym_id(location), auth_asym_id: p.chain.auth_asym_id(location),
        label_seq_id: p.residue.label_seq_id(location) > 0 ? p.residue.label_seq_id(location) : null, auth_seq_id: p.residue.auth_seq_id(location),
        insertion_code: p.residue.pdbx_PDB_ins_code(location), comp_id: p.atom.label_comp_id(location),
        atom_id: p.atom.label_atom_id(location), instance_id: location.unit.conformation.operator.instanceId,
        model_id: location.unit.model.modelNum,
      };
      el("selection").textContent = `${selection.comp_id} · author chain ${selection.auth_asym_id} residue ${selection.auth_seq_id}${selection.insertion_code} · label chain ${selection.label_asym_id}${selection.label_seq_id === null ? "" : ` residue ${selection.label_seq_id}`}`;
      void publish({ status: "selection", selection }).catch(error => status(String(error), true));
    });
    buttons(true);
  } catch (error) {
    if (disposed || token !== revision) return;
    const message = error instanceof Error ? error.message : String(error);
    status(`Could not load the molecular view: ${message}`, true);
    // A valid artifact remains downloadable even when coordinate retrieval fails.
    buttons(true);
    await publish({ status: "error", pdb_id: currentScene()?.builder.pdb_id ?? result.builder?.pdb_id, error: message });
  }
}

function receive(result: ToolResult): void {
  const token = ++revision;
  buttons(false);
  if (result.isError) {
    scene = undefined;
    status(result.content?.filter(c => c.type === "text").map(c => c.text).join("\n") || "Scene construction failed.", true);
    return;
  }
  const data = result._meta?.mvs as SceneResult | undefined;
  if (!data?.mvsj || data.version !== 1 || !(data.builder && Array.isArray(data.legend) || data.story && Array.isArray(data.scenes))) {
    scene = undefined;
    status("No supported MVS scene was returned by the tool.", true);
    return;
  }
  work = work.then(() => load(data, token)).catch(error => status(String(error), true));
}

el("reset").addEventListener("click", () => { if (scene) receive({ _meta: { mvs: scene } }); });
el("download").addEventListener("click", () => {
  if (!scene) return;
  const current = scene;
  const name = current.story ? "molecular-story.mvsj" : `${current.builder?.pdb_id ?? "molecular-scene"}.mvsj`;
  void (async () => {
    if (connected && app.getHostCapabilities()?.downloadFile) {
      const result = await app.downloadFile({ contents: [{ type: "resource", resource: {
        uri: `mvs://pdbe/${name}`, mimeType: "application/json", text: JSON.stringify(current.mvsj, null, 2),
      } }] });
      if (result.isError) throw new Error("The host could not save the MVSJ file");
    } else {
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
      downloadUrl = URL.createObjectURL(new Blob([JSON.stringify(current.mvsj, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = downloadUrl; link.download = name; link.click();
    }
  })().catch(error => status(String(error), true));
});

app.ontoolinputpartial = () => status("Preparing the molecular scene…");
app.ontoolinput = () => status("Building and validating the molecular scene…");
app.ontoolresult = receive;
app.ontoolcancelled = () => { ++revision; scene = undefined; buttons(false); status("Scene request cancelled."); };
app.onhostcontextchanged = theme;
app.onteardown = async () => {
  disposed = true; ++revision;
  viewer?.dispose(); viewer = undefined;
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  return {};
};
void app.connect().then(() => {
  connected = true;
  const context = app.getHostContext();
  if (context) theme(context);
}).catch(() => status("Open this tool in an MCP Apps host to receive a molecular scene.", true));
