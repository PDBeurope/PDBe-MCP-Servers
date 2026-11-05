/** One Mol* runtime, shared by Explorer, Comparison, Builder, and workspace updates. */
import { Viewer } from "molstar-mvs/lib/apps/viewer/app.js";
import { createViewerSpec } from "molstar-mvs/lib/apps/viewer/plugin-spec.js";
import { ViewerAutoPreset } from "molstar-mvs/lib/apps/viewer/presets.js";
import { createPluginUI } from "molstar-mvs/lib/mol-plugin-ui/index.js";
import { renderReact18 } from "molstar-mvs/lib/mol-plugin-ui/react18.js";
import { ViewportSnapshotDescription } from "molstar-mvs/lib/mol-plugin-ui/controls.js";
import type { Structure } from "molstar-mvs/lib/mol-model/structure/structure.js";
import { createElement } from "react";
import { createPortal } from "react-dom";

export async function createWorkspaceViewer(target: HTMLElement, caption: HTMLElement, showCaption: () => boolean): Promise<Viewer> {
  const spec = createViewerSpec({ layoutIsExpanded: false, layoutShowControls: false, layoutShowSequence: false,
    layoutShowLog: false, layoutShowLeftPanel: false, viewportShowExpand: false, viewportShowToggleFullscreen: false,
    volumeStreamingDisabled: true, extensions: ["mvs"], pdbProvider: "pdbe" });
  spec.components = { ...spec.components, viewport: { ...spec.components?.viewport,
    snapshotDescription: () => showCaption() ? createPortal(createElement(ViewportSnapshotDescription), caption) : null,
  } };
  const plugin = await createPluginUI({ target, spec, render: renderReact18,
    onBeforeUIRender: p => p.builders.structure.representation.registerPreset(ViewerAutoPreset) });
  return new Viewer(plugin);
}
export function displayedStructure(viewer: Viewer, id: string): Structure | undefined {
  for (const cell of viewer.plugin.state.data.cells.values()) {
    if (cell.transform.tags?.includes(`mvs-ref:${id}`) && cell.obj?.data?.units) return cell.obj.data as Structure;
  }
  return undefined;
}
