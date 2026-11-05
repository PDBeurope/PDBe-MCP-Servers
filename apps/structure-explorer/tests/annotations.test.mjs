import assert from "node:assert/strict";
import test from "node:test";
import { annotationsAt, annotationTooltips, buildVisualData } from "../src/annotations.ts";

const domain = { id: "domain", kind: "domains", source: "InterPro", accession: "IPR1", name: "<Domain>", description: "", source_url: "source", segments: [
  { label_asym_id: "X", auth_asym_id: "A", start: 1, end: 3, details: {} },
  { label_asym_id: "X", auth_asym_id: "A", start: 7, end: 9, details: {} },
] };

test("discontinuous ranges and chain scope remain separate", () => {
  assert.equal(annotationsAt([domain], "X", 2).length, 1);
  assert.equal(annotationsAt([domain], "X", 5).length, 0);
  assert.equal(annotationsAt([domain], "Y", 2).length, 0);
  assert.equal(annotationsAt([domain], "X", null).length, 0);
});
test("tooltips escape markup and retain separate ranges", () => {
  const data = annotationTooltips([domain]);
  assert.equal(data.length, 2);
  assert.ok(data[0].tooltip.includes("&lt;Domain&gt;"));
  assert.equal(data[1].beg_label_seq_id, 7);
});
test("selection overlays domains, clearing selection restores domain colours", () => {
  const selected = { label_asym_id: "X", auth_seq_id: 103, pdbx_PDB_ins_code: "B" };
  const data = buildVisualData([domain], ["X", "Y"], new Set(["Y"]), selected);
  assert.equal(data[0].beg_label_seq_id, 1);
  assert.equal(data[1].beg_label_seq_id, 7);
  assert.equal(data.at(-1).pdbx_PDB_ins_code, "B");
  assert.equal(data.find(item => item.label_asym_id === "Y").opacity, 0);
  const cleared = buildVisualData([domain], ["X", "Y"], new Set(["Y"]));
  assert.deepEqual(cleared.slice(0, 2), data.slice(0, 2));
  assert.equal(cleared.length, data.length - 1);
  assert.ok(!buildVisualData([domain], ["X"], new Set(["X"]), selected).some(item => item.sideChain));
});
