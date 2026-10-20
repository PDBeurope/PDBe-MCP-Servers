import { App, applyDocumentTheme, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";
import "pdbe-molstar/build/pdbe-molstar-plugin.js";
import type { PDBeMolstarPlugin } from "pdbe-molstar/lib/viewer";
import type { QueryParam } from "pdbe-molstar/lib/helpers";
import { alphaCarbons, comparisonCsv, displacementColor, measurePairs, mvsMatrix,
  type AlphaCarbon, type ComparisonData, type ComparisonSide, type Measurement } from "./comparison";
import "pdbe-molstar/build/pdbe-molstar-light.css";
import "./style.css";
import "./comparison.css";

function el<T extends HTMLElement = HTMLElement>(id: string): T { return document.getElementById(id) as T; }
function status(message: string, error = false) {
  el("status").textContent = message;
  el("status").classList.toggle("error", error);
}
function fail(error: unknown) { status(error instanceof Error ? error.message : String(error), true); }
const app = new App({ name: "PDBe Structure Comparison Workbench", version: "0.1.0" });
let viewer: PDBeMolstarPlugin | undefined;
let data: ComparisonData | undefined;
let rows: Measurement[] = [];
let selected: Measurement | undefined;
let measurements: ReturnType<typeof measurePairs> | undefined;
let connected = false, busy = false, requesting = false, disposed = false, ready = false;
let work = Promise.resolve();
let visuals = Promise.resolve();
let fingerprint = "";
let downloadUrl: string | undefined;
let atoms: { reference: Map<number, AlphaCarbon>; mobile: Map<number, AlphaCarbon> } | undefined;

function controls() {
  el<HTMLButtonElement>("compare").disabled = !connected || busy || requesting || disposed;
  for (const id of ["reset", "show-reference", "show-mobile", "colour", "export"]) {
    (el(id) as HTMLButtonElement | HTMLInputElement | HTMLSelectElement).disabled = !ready || busy || requesting || disposed;
  }
  el<HTMLButtonElement>("ask").disabled = !ready || busy || requesting || !selected || !app.getHostCapabilities()?.message;
}
function runVisual(action: () => Promise<void>) {
  visuals = visuals.then(async () => { if (ready && !busy && !disposed) await action(); }).catch(fail);
}
function residueText(r: Measurement["reference"], actual?: string | null) {
  return `${actual ?? r.comp_id} ${r.label_seq_id} / ${r.auth_seq_id ?? "?"}${r.insertion_code}`;
}
function sideText(side: ComparisonSide) {
  return `${side.pdb_id.toUpperCase()} · label ${side.chain.label_asym_id} / author ${side.chain.auth_asym_id}`;
}
function selectionPayload(row: Measurement) {
  return { uniprot_accession: data!.uniprot_accession, uniprot_position: row.uniprot_position,
    displacement_angstrom: row.displacement,
    reference: { pdb_id: data!.reference.pdb_id, ...data!.reference.chain, ...row.reference,
      comp_id: row.reference_comp_id ?? row.reference.comp_id,
      model_id: viewer?.getStructure(1)?.cell.obj?.data.models[0]?.modelNum,
      atom_ids: ["CA"], altloc: row.reference_altloc },
    mobile: { pdb_id: data!.mobile.pdb_id, ...data!.mobile.chain, ...row.mobile,
      comp_id: row.mobile_comp_id ?? row.mobile.comp_id,
      model_id: viewer?.getStructure(2)?.cell.obj?.data.models[0]?.modelNum,
      atom_ids: ["CA"], altloc: row.mobile_altloc } };
}
async function publish() {
  if (connected && app.getHostCapabilities()?.updateModelContext && data && measurements) {
    await app.updateModelContext({ structuredContent: {
      pdbe_comparison: { reference: sideText(data.reference), mobile: sideText(data.mobile),
        uniprot_accession: data.uniprot_accession, segment: data.segment, method: data.method,
        rmsd_angstrom: measurements.rmsd, observed_ca_pairs: measurements.measured_count,
        mapped_pairs: data.mapped_pair_count, metric_sources: measurements.metric_sources,
        sources: data.sources, retrieved_at: data.retrieved_at },
      pdbe_comparison_selection: selected ? selectionPayload(selected) : null,
    } });
  }
}
async function colour() {
  if (!viewer || !data) return;
  const displacement = el<HTMLSelectElement>("colour").value === "displacement";
  for (const [index, key, base] of [[1, "reference", "#2787b5"], [2, "mobile", "#db4a39"]] as const) {
    const side = data[key];
    const items: (QueryParam & { color: string })[] = displacement ? rows.map(r => ({ label_asym_id: side.chain.label_asym_id,
      label_seq_id: r[key].label_seq_id,
      color: displacementColor(r.displacement) })) : [{ label_asym_id: side.chain.label_asym_id, color: base }];
    if (selected) items.push({ label_asym_id: side.chain.label_asym_id,
      label_seq_id: selected[key].label_seq_id,
      color: "#f0c838" });
    await viewer.visual.select({ structureNumber: index, data: items, nonSelectedColor: displacement ? "#b7b7b7" : base });
  }
}
async function select(row: Measurement, focus: boolean) {
  selected = row;
  el("selection").textContent = `UniProt ${row.uniprot_position} · reference ${residueText(row.reference, row.reference_comp_id)} · comparison ${residueText(row.mobile, row.mobile_comp_id)} · ${row.displacement === null ? "Cα pair unavailable" : `${row.displacement.toFixed(3)} Å displacement`}`;
  for (const item of document.querySelectorAll<HTMLElement>("[data-position]")) {
    const active = Number(item.dataset.position) === row.uniprot_position;
    item.classList.toggle("selected", active);
    if (item.tagName === "BUTTON") item.setAttribute("aria-pressed", String(active));
  }
  await colour();
  if (focus && viewer && data && atoms) {
    // Use Mol*'s displayed coordinates and native camera boundary calculation.
    const points = (["reference", "mobile"] as const).flatMap(key => {
      const atom = atoms![key].get(row[key].label_seq_id);
      return atom && el<HTMLInputElement>(`show-${key}`).checked ? [atom.position] : [];
    });
    if (points.length) {
      viewer.plugin.managers.camera.focusSpheres(points, center => ({ center, radius: 6 }), { minRadius: 8 });
    }
  }
  controls();
  await publish();
}

function renderRows() {
  el("rows").replaceChildren(); el("chart").replaceChildren();
  const bars = document.createElement("div"); bars.className = "chart-bars";
  const max = Math.max(1, ...rows.map(r => r.displacement ?? 0));
  for (const row of rows) {
    const tr = document.createElement("tr"); tr.dataset.position = String(row.uniprot_position);
    const td = document.createElement("td"), button = document.createElement("button");
    button.textContent = String(row.uniprot_position);
    button.addEventListener("click", () => runVisual(() => select(row, true)));
    td.append(button); tr.append(td);
    for (const text of [residueText(row.reference, row.reference_comp_id), residueText(row.mobile, row.mobile_comp_id), row.displacement?.toFixed(3) ?? "Unavailable"]) {
      const cell = document.createElement("td"); cell.textContent = text; tr.append(cell);
    }
    el("rows").append(tr);
    const bar = document.createElement("button");
    bar.type = "button"; bar.dataset.position = String(row.uniprot_position); bar.setAttribute("aria-pressed", "false");
    bar.title = `UniProt ${row.uniprot_position}: ${row.displacement?.toFixed(3) ?? "unavailable"} Å`;
    bar.setAttribute("aria-label", bar.title);
    bar.style.height = `${row.displacement === null ? 3 : Math.max(3, row.displacement / max * 110)}px`;
    bar.style.backgroundColor = displacementColor(row.displacement);
    bar.addEventListener("click", () => runVisual(() => select(row, true)));
    bars.append(bar);
  }
  el("chart").append(bars);
}

async function load(value: ComparisonData) {
  if (disposed) return;
  busy = true; ready = false; controls();
  await visuals;
  try {
    status("Loading coordinates and PDBe precomputed alignment…");
    viewer?.plugin.dispose(); viewer = undefined;
    data = value; rows = []; selected = undefined; measurements = undefined; atoms = undefined;
    el("rows").replaceChildren(); el("chart").replaceChildren();
    el("selection").textContent = "Select a chart bar, table row, or residue in either structure.";
    el("rmsd").textContent = "—";
    el("coverage").textContent = "Coordinate-derived coverage is pending.";
    el("csv").hidden = true; el("csv-label").hidden = true;
    el<HTMLInputElement>("show-reference").checked = true; el<HTMLInputElement>("show-mobile").checked = true;
    el<HTMLSelectElement>("colour").value = "structure";
    for (const key of ["reference", "mobile"] as const) {
      el<HTMLInputElement>(`${key}-pdb`).value = value[key].pdb_id;
      el<HTMLInputElement>(`${key}-chain`).value = value[key].chain.label_asym_id;
    }
    el<HTMLInputElement>("uniprot").value = value.uniprot_accession;
    el<HTMLInputElement>("segment").value = String(value.segment.index);
    el("comparison-summary").hidden = false;
    el("comparison-title").textContent = `${sideText(value.reference)} ↔ ${sideText(value.mobile)}`;
    el("scope").textContent = `${value.uniprot_accession} · PDBe segment ${value.segment.index}: ${value.segment.start}–${value.segment.end}. Source clusters ${value.reference.cluster_indices.join(", ")} and ${value.mobile.cluster_indices.join(", ")}. Full selected chains are shown; scores cover this segment only.`;
    el("method").textContent = value.method;
    el("warnings").textContent = value.warnings.join(" ");
    el("sources").replaceChildren();
    for (const url of value.sources) {
      const li = document.createElement("li"), link = document.createElement("a");
      link.textContent = url; link.href = url; link.target = "_blank"; link.rel = "noreferrer";
      link.addEventListener("click", event => { event.preventDefault(); void app.openLink({ url }).catch(fail); });
      li.append(link); el("sources").append(li);
    }
    el("retrieved").textContent = `Retrieved ${value.retrieved_at}`;
    el("viewer").replaceChildren();
    const Viewer = window.PDBeMolstarPlugin as typeof PDBeMolstarPlugin;
    viewer = new Viewer();
    await viewer.render(el("viewer"), { hideControls: true, bgColor: { r: 255, g: 255, b: 255 },
      pdbeLink: false, loadMaps: false, selectInteraction: false, granularity: "residue" });
    if (disposed) return;
    const mvs = Viewer.extensions.MVS;
    const builder = mvs.MVSData.createBuilder();
    for (const [key, color] of [["reference", "#2787b5"], ["mobile", "#db4a39"]] as const) {
      const side = value[key];
      builder.download({ url: side.coordinate_url }).parse({ format: "bcif" })
        .modelStructure({ model_index: 0, ref: key }).transform({ matrix: mvsMatrix(side.matrix) })
        .component({ selector: { label_asym_id: side.chain.label_asym_id } })
        .representation({ type: "cartoon" }).color({ color });
    }
    await mvs.loadMVS(viewer.plugin, builder.getState(), { sanityChecks: true });
    if (disposed) return;
    // Read the transformed cells; hierarchy root cells contain deposited coordinates.
    const a = viewer.getStructure(1)?.transform?.cell.obj?.data;
    const b = viewer.getStructure(2)?.transform?.cell.obj?.data;
    if (!a || !b) throw new Error("Both PDBe-transformed structures must load before Mol* can measure this comparison.");
    value.reference.model_id = a.models[0]?.modelNum; value.mobile.model_id = b.models[0]?.modelNum;
    atoms = { reference: alphaCarbons(a, value.reference.chain.label_asym_id), mobile: alphaCarbons(b, value.mobile.chain.label_asym_id) };
    measurements = measurePairs(value, atoms.reference, atoms.mobile);
    rows = measurements.rows;
    el("rmsd").textContent = measurements.rmsd === null ? "Unavailable" : `${measurements.rmsd.toFixed(3)} Å`;
    el("coverage").textContent = `${measurements.measured_count} observed Cα pairs / ${value.mapped_pair_count} SIFTS-mapped pairs · UniProt segment ${value.segment.start}–${value.segment.end}.`;
    renderRows(); ready = true;
    await viewer.visual.reset({ camera: true });
    await publish();
    status(measurements.rmsd === null ? "Alignment loaded; fewer than three observed Cα pairs. RMSD unavailable." : "Aligned structures ready · select a residue to inspect both structures.");
  } catch (error) { fingerprint = ""; fail(error); }
  finally { busy = false; controls(); }
}

function receive(result: { isError?: boolean; content?: { type: string; text?: string }[]; _meta?: Record<string, unknown> }) {
  if (result.isError) { fail(result.content?.map(c => c.text ?? "").join("\n") ?? "Comparison request failed."); return; }
  const value = result._meta?.comparison as ComparisonData | undefined;
  if (!value) return;
  const id = `${value.retrieved_at}/${value.uniprot_accession}/${value.segment.index}/${value.reference.pdb_id}/${value.reference.chain.label_asym_id}/${value.mobile.pdb_id}/${value.mobile.chain.label_asym_id}`;
  if (fingerprint === id) return;
  fingerprint = id;
  work = work.then(() => load(value)).catch(fail);
}
app.ontoolresult = receive;
app.ontoolinputpartial = () => status("Preparing structure comparison…");
app.ontoolinput = () => status("Fetching PDBe superposition and SIFTS correspondence…");
app.ontoolcancelled = () => status("Comparison request cancelled.");
app.onerror = fail;
app.onhostcontextchanged = context => {
  if (context.theme) applyDocumentTheme(context.theme);
  if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
};
app.onteardown = async () => {
  disposed = true; ready = false; controls();
  await work; await visuals;
  viewer?.plugin.dispose(); viewer = undefined;
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  return {};
};
el<HTMLFormElement>("compare-form").addEventListener("submit", event => {
  event.preventDefault();
  if (busy || requesting || disposed) return;
  requesting = true; controls(); status("Fetching PDBe comparison data…");
  const args: Record<string, string | number> = {};
  for (const side of ["reference", "mobile"]) {
    args[`${side}_pdb_id`] = el<HTMLInputElement>(`${side}-pdb`).value.trim();
    args[`${side}_chain_id`] = el<HTMLInputElement>(`${side}-chain`).value.trim();
  }
  if (el<HTMLInputElement>("uniprot").value.trim()) args.uniprot_accession = el<HTMLInputElement>("uniprot").value.trim();
  if (el<HTMLInputElement>("segment").value) args.segment_index = Number(el<HTMLInputElement>("segment").value);
  void app.callServerTool({ name: "ebi.pdbe.compare_structures", arguments: args }).then(receive).catch(fail)
    .finally(() => { requesting = false; controls(); });
});
for (const id of ["reference-pdb", "reference-chain", "mobile-pdb", "mobile-chain"]) {
  el(id).addEventListener("input", () => {
    el<HTMLInputElement>("uniprot").value = "";
    el<HTMLInputElement>("segment").value = "";
  });
}
el("reset").addEventListener("click", () => runVisual(async () => { selected = undefined; await colour(); await viewer!.visual.reset({ camera: true }); el("selection").textContent = "Select a chart bar, table row, or residue in either structure."; renderRows(); controls(); await publish(); }));
el("colour").addEventListener("change", () => runVisual(colour));
for (const [index, key] of [[1, "reference"], [2, "mobile"]] as const) {
  el(`show-${key}`).addEventListener("change", () => runVisual(async () => {
    await viewer!.visual.structureVisibility(index, el<HTMLInputElement>(`show-${key}`).checked);
  }));
}
el("viewer").addEventListener("PDB.molstar.click", event => {
  if (!data || busy || !ready) return;
  const item = (event as Event & { eventData?: { entry_id?: string; label_asym_id?: string; seq_id?: number } }).eventData;
  if (!item) return;
  const key = (["reference", "mobile"] as const).find(k => data![k].pdb_id.toLowerCase() === item.entry_id?.toLowerCase() && data![k].chain.label_asym_id === item.label_asym_id);
  const row = key ? rows.find(r => r[key].label_seq_id === item.seq_id) : undefined;
  if (row) runVisual(() => select(row, false));
});
el("export").addEventListener("click", () => {
  if (!data || !ready) return;
  const csv = comparisonCsv(data, rows);
  el<HTMLTextAreaElement>("csv").value = csv; el("csv").hidden = false; el("csv-label").hidden = false;
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a"); link.href = downloadUrl;
  link.download = `${data.reference.pdb_id}-${data.mobile.pdb_id}-pdbe-comparison.csv`;
  document.body.append(link); link.click(); link.remove();
});
el("ask").addEventListener("click", () => {
  if (!selected || !data) return;
  void app.sendMessage({ role: "user", content: [{ type: "text", text: `Explain the structural evidence for this PDBe-aligned residue pair: ${JSON.stringify(selectionPayload(selected))}. Alignment method: ${data.method}` }] }).catch(fail);
});
await app.connect();
connected = true;
const context = app.getHostContext();
if (context?.theme) applyDocumentTheme(context.theme);
if (context?.styles?.variables) applyHostStyleVariables(context.styles.variables);
controls();
if (!data) status("Ready · compare two protein chains with a shared PDBe superposition.");
