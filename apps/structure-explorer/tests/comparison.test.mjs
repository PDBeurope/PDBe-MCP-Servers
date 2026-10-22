import assert from "node:assert/strict";
import test from "node:test";
import { comparisonCsv } from "../src/comparison.ts";
const data = {
  reference: { pdb_id: "1abc", chain: { label_asym_id: "A", auth_asym_id: "X" }, matrix: [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]] },
  mobile: { pdb_id: "2abc", chain: { label_asym_id: "B", auth_asym_id: "Y" }, matrix: [[1,0,0,10],[0,1,0,20],[0,0,1,30],[0,0,0,1]] },
  uniprot_accession: "P12345", segment: { index: 1 }, mapped_pair_count: 2,
  pairs: [{ uniprot_position: 42, reference: { label_seq_id: 3, auth_seq_id: 103, insertion_code: "C", comp_id: "ALA" }, mobile: { label_seq_id: 7, auth_seq_id: 207, insertion_code: "", comp_id: "GLY" } },
    { uniprot_position: 43, reference: { label_seq_id: 4, auth_seq_id: 104, insertion_code: "", comp_id: "SER" }, mobile: { label_seq_id: 8, auth_seq_id: 208, insertion_code: "", comp_id: "THR" } }],
  method: "PDBe precomputed transforms; SIFTS mapping", sources: ["https://example.test/mapping"], retrieved_at: "2026-10-22",
};
test("exports every supplied residue pair, insertion code, transform and provenance without geometric measurements", () => {
  const csv = comparisonCsv(data);
  assert.equal(csv.split("\r\n").length, 3);
  assert.match(csv, /"42"/); assert.match(csv, /"103","C","ALA"/);
  assert.match(csv, /PDBe precomputed transforms/); assert.match(csv, /https:\/\/example.test\/mapping/);
  assert.doesNotMatch(csv, /rmsd|displacement|metric_sources|observed_ca|altloc/i);
});
test("correspondence export preserves spreadsheet formula protection", () => {
  const csv = comparisonCsv({...data, method: "=unsafe()"});
  assert.match(csv, /'\=unsafe/);
});
