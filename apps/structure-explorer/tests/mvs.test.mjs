import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
// Use the package's Node entry points; its browser ESM graph has cycles that
// require bundler ordering when importing component creation helpers.
const require = createRequire(import.meta.url);
const { MVSData } = require("molstar-mvs/lib/commonjs/extensions/mvs/mvs-data.js");
const { parsePDB } = require("molstar-mvs/lib/commonjs/mol-io/reader/pdb/parser.js");
const { trajectoryFromPDB } = require("molstar-mvs/lib/commonjs/mol-model-formats/structure/pdb.js");
const { Structure } = require("molstar-mvs/lib/commonjs/mol-model/structure/structure.js");
const { createStructureComponent } = require("molstar-mvs/lib/commonjs/mol-plugin-state/helpers/structure-component.js");
const { componentPropsFromSelector } = require("molstar-mvs/lib/commonjs/extensions/mvs/load-helpers.js");

// Also checked against the live Python compiler in tests/test_mvs.py. These
// cases detect format drift between server output and the pinned viewer.
const fixtures = JSON.parse(readFileSync(new URL("../../../tests/fixtures/mvs_scenes.json", import.meta.url), "utf8"));
const story = JSON.parse(readFileSync(new URL("../../../tests/fixtures/mvs_story.json", import.meta.url), "utf8"));
test("Mol* 5.13.1 accepts the complete Python story with native snapshot metadata", () => {
  assert.equal(MVSData.validationIssues(story.mvsj, { noExtra: true }), undefined);
  assert.equal(story.mvsj.kind, "multiple");
  assert.deepEqual(story.mvsj.snapshots.map(s => s.metadata.key), ["overview", "ligand"]);
});
for (const fixture of fixtures) {
  test(`Mol* 5.13.1 accepts Python MVS: ${fixture.name}`, () => {
    assert.equal(MVSData.validationIssues(fixture.mvsj, { noExtra: true }), undefined);
  });
}

const extended = JSON.parse(readFileSync(new URL("../../../tests/fixtures/mvs_extended.json", import.meta.url), "utf8"));
for (const fixture of extended) {
  test(`Mol* accepts expanded builder APIs: ${fixture.name}`, () => {
    assert.equal(MVSData.validationIssues(fixture.mvsj, { noExtra: true }), undefined);
  });
}

test("MolQL symbol signatures match the pinned viewer runtime", () => {
  const { DefaultQueryRuntimeTable } = require("molstar-mvs/lib/commonjs/mol-script/runtime/query/compiler.js");
  const signatures = Object.fromEntries([...DefaultQueryRuntimeTable.map].map(([name, { symbol: s }]) => [name, {
    args: s.args.kind === "dictionary" && !Object.values(s.args.map).some(a => a.isRest) ? Object.keys(s.args.map) : null,
    required: s.args.kind === "dictionary" ? Object.entries(s.args.map).filter(([, a]) => !a.isOptional && !a.isRest).map(([key]) => key) : [],
    query: s.type.alias === "ElementSelectionQuery",
  }]));
  const served = JSON.parse(readFileSync(new URL("../../../pdbe_mcp_server/skills/molview-spec/references/molql-symbols.json", import.meta.url), "utf8"));
  assert.deepEqual(served, signatures);
});

const pdb = [
  "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C  ",
  "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C  ",
  "ATOM      3  CA  SER A   3       0.000   1.000   0.000  1.00 20.00           C  ",
  "HETATM    4  C1  RET B 501       2.000   1.000   0.000  1.00 20.00           C  ",
  "HETATM    5  O   HOH C 601       3.000   1.000   0.000  1.00 20.00           O  ",
  "END",
].join("\n");
const parsed = await parsePDB(pdb, "test").run();
assert.equal(parsed.isError, false);
const trajectory = await trajectoryFromPDB(parsed.result).run();
const structure = Structure.ofModel(trajectory.representative);
function atomCount(selector) {
  const component = createStructureComponent(structure, {
    type: componentPropsFromSelector(selector), label: "Test", nullIfEmpty: false,
  }, {});
  return component.data.elementCount;
}
function components(node) {
  return [...(node.kind === "component" ? [node] : []), ...(node.children ?? []).flatMap(components)];
}
test("Python residue and ligand selectors resolve to the expected atoms in Mol*", () => {
  const selectors = components(fixtures.find(f => f.name === "highlight and focus").mvsj.root).map(n => n.params.selector);
  assert.equal(atomCount(selectors[0]), 2);
  assert.equal(atomCount(selectors[1]), 1);
  assert.equal(atomCount({ auth_asym_id: "DOES_NOT_EXIST" }), 0);
});
test("grouped annotations select the union and broad all excludes water", () => {
  const grouped = components(fixtures.find(f => f.name === "annotation group").mvsj.root).at(-1);
  assert.equal(atomCount(grouped.params.selector), 2);
  const broad = components(fixtures.find(f => f.name === "non-water broad selection").mvsj.root);
  assert.equal(broad.reduce((sum, node) => sum + atomCount(node.params.selector), 0), 4);
  assert.equal(structure.elementCount, 5);
});

test("expanded MolQL selectors select and color the expected residue", () => {
  const root = extended.find(f => f.name === "MolQL selections and colors").mvsj.root;
  const component = components(root)[0];
  assert.equal(atomCount(component.params.selector), 1);
  const colorSelector = component.children.find(n => n.kind === "representation").children.find(n => n.kind === "color").params.selector;
  assert.equal(atomCount(colorSelector), 1);
});
