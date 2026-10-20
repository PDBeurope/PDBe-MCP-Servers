import type { QueryParam } from "pdbe-molstar/lib/helpers";

export interface AnnotationSegment {
  label_asym_id: string;
  auth_asym_id: string;
  start: number;
  end: number;
  details: Record<string, unknown>;
}
export interface Annotation {
  id: string;
  kind: string;
  source: string;
  accession: string;
  name: string;
  description: string;
  source_url: string;
  segments: AnnotationSegment[];
}
export type VisualItem = QueryParam & {
  color?: string | null;
  opacity?: number;
  sideChain?: boolean;
  focus?: boolean;
};
const palette = ["#268b96", "#9473bc", "#d58a3f", "#609c5d", "#c76b89", "#527fc1"];
export function annotationColor(index: number): string { return palette[index % palette.length]; }
export function segmentQuery(segment: AnnotationSegment): QueryParam {
  return { label_asym_id: segment.label_asym_id, beg_label_seq_id: segment.start, end_label_seq_id: segment.end };
}
export function annotationsAt(features: Annotation[], chain: string, residue: number | null): { feature: Annotation; segment: AnnotationSegment }[] {
  if (residue === null) return [];
  return features.flatMap(feature => feature.segments
    .filter(s => s.label_asym_id === chain && s.start <= residue && residue <= s.end)
    .map(segment => ({ feature, segment })));
}
export function detailText(details: Record<string, unknown>): string {
  return Object.entries(details).filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`).join(" · ");
}
function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);
}
export function annotationTooltips(features: Annotation[]): (QueryParam & { tooltip: string })[] {
  return features.flatMap(feature => feature.segments.map(segment => ({
    ...segmentQuery(segment),
    tooltip: escapeHtml(`${feature.source} · ${feature.accession} · ${feature.name}${feature.description ? ` · ${feature.description}` : ""}${Object.keys(segment.details).length ? ` · ${detailText(segment.details)}` : ""}`),
  })));
}
export function buildVisualData(
  features: Annotation[], chains: string[], hidden: Set<string>, selected?: QueryParam, focus = false,
): VisualItem[] {
  const data: VisualItem[] = features.flatMap((feature, index) => feature.segments
    .map(segment => ({ ...segmentQuery(segment), color: annotationColor(index) })));
  data.push(...chains.map(chain => ({ label_asym_id: chain, opacity: hidden.has(chain) ? 0 : 1, color: null })));
  if (selected && !hidden.has(selected.label_asym_id ?? "")) {
    data.push({ ...selected, color: "#ee9851", sideChain: true, focus });
  }
  return data;
}
