import assert from "node:assert/strict";
import test from "node:test";
import { parsePDB } from "molstar/lib/mol-io/reader/pdb/parser.js";
import { trajectoryFromPDB } from "molstar/lib/mol-model-formats/structure/pdb.js";
import { Structure } from "molstar/lib/mol-model/structure/structure.js";
import { alphaCarbons, comparisonCsv, measurePairs, mvsMatrix } from "../src/comparison.ts";

// A non-collinear chain with competing Cα altlocs on residue 1. Mol*'s trace
// selection must be honoured even though its selected altloc has lower occupancy.
const pdb = [
  "ATOM      1  CA AALA A   1       0.000   0.000   0.000  0.40 20.00           C  ",
  "ATOM      2  CA BALA A   1      20.000   0.000   0.000  0.60 20.00           C  ",
  "ATOM      3  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C  ",
  "ATOM      4  CA  SER A   3       0.000   1.000   0.000  1.00 20.00           C  ",
  "END",
].join("\n");
const parsed = await parsePDB(pdb, "1abc").run();
assert.equal(parsed.isError, false);
const trajectory = await trajectoryFromPDB(parsed.result).run();
const structure = Structure.ofModel(trajectory.representative);
const chain = trajectory.representative.atomicHierarchy.chains.label_asym_id.value(0);
const referenceMatrix = [[0, -1, 0, 10], [1, 0, 0, 20], [0, 0, 1, 30], [0, 0, 0, 1]];
const mobileMatrix = [[0, -1, 0, 13], [1, 0, 0, 24], [0, 0, 1, 30], [0, 0, 0, 1]];
const reference = alphaCarbons(Structure.transform(structure, mvsMatrix(referenceMatrix)), chain);
const mobile = alphaCarbons(Structure.transform(structure, mvsMatrix(mobileMatrix)), chain);
const residue = n => ({ label_seq_id: n, auth_seq_id: n, insertion_code: "", comp_id: "ALA" });
const side = matrix => ({ pdb_id: "1abc", chain: { label_asym_id: chain, auth_asym_id: "A" }, matrix });
const data = {
  reference: side(referenceMatrix), mobile: side(mobileMatrix), uniprot_accession: "P69905",
  segment: { index: 1, start: 1, end: 3 }, mapped_pair_count: 3,
  pairs: [1, 2, 3].map(n => ({ uniprot_position: n, reference: residue(n), mobile: residue(n) })),
  method: "PDBe alignment; Mol* distances and RMS", sources: [], retrieved_at: "2026-10-19",
};

test("uses Mol* trace atoms and displayed coordinates with the supplied transform applied once", () => {
  assert.equal(reference.size, 3);
  assert.equal(reference.get(1).altloc, "A");
  assert.deepEqual([...reference.get(1).position], [10, 20, 30]);
  assert.deepEqual([...reference.get(2).position], [10, 21, 30]);
  assert.deepEqual([...mobile.get(1).position], [13, 24, 30]);
  assert.equal(alphaCarbons(structure, "absent-chain").size, 0);
});

test("preserves PDBe-frame displacement instead of silently calculating a new optimal fit", () => {
  const result = measurePairs(data, reference, mobile);
  assert.deepEqual(result.rows.map(row => row.displacement), [5, 5, 5]);
  assert.equal(result.rmsd, 5); // A new best fit would erase the translation and give zero.
  assert.equal(result.metric_sources.displacement, "Mol* Vec3.distance");
  assert.match(result.metric_sources.rmsd, /Mol\* arrayRms/);
  const csv = comparisonCsv(data, result.rows);
  assert.match(csv, /metric_sources/);
  assert.match(csv, /Mol\* Vec3.distance/);
});

test("missing trace atoms remain unavailable and coverage has counts only", () => {
  const missing = new Map(mobile);
  missing.delete(2);
  const result = measurePairs(data, reference, missing);
  assert.equal(result.measured_count, 2);
  assert.equal(result.rows[1].displacement, null);
  assert.equal(result.rows[1].mobile_altloc, null);
  assert.equal(result.rmsd, null);
  assert.equal("mapped_ca_coverage" in result, false);
  assert.equal("segment_ca_coverage" in result, false);
});
