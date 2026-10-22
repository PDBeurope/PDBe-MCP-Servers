import assert from 'node:assert/strict';
import test from 'node:test';
import { parsePDB } from 'molstar-mvs/lib/mol-io/reader/pdb/parser.js';
import { trajectoryFromPDB } from 'molstar-mvs/lib/mol-model-formats/structure/pdb.js';
import { Structure } from 'molstar-mvs/lib/mol-model/structure/structure.js';
import { coordinateInventory, attachLayerRefs } from '../src/workspace-capabilities.ts';
import { validateEnvelope, checkRevision } from '../src/workspace.ts';

function atom(serial, name, comp, chain, residue, x, symbol = 'C', occupancy = 1, insertion = '') {
  return `${comp === 'ALA' ? 'ATOM  ' : 'HETATM'}${String(serial).padStart(5)} ${name.padStart(4)} ${comp.padStart(3)} ${chain}${String(residue).padStart(4)}${insertion || ' '}   ${x.toFixed(3).padStart(8)}${'0.000'.padStart(8)}${'0.000'.padStart(8)}${occupancy.toFixed(2).padStart(6)} 20.00          ${symbol.padStart(2)}  `;
}
const parsed = await parsePDB([
  atom(1, 'CA', 'ALA', 'A', 101, 0), atom(2, 'CA', 'ALA', 'A', 102, 5),
  atom(3, 'CA', 'ALA', 'A', 103, 5.01), atom(4, 'CA', 'ALA', 'A', 104, 10),
  atom(5, 'CA', 'ALA', 'B', 101, 0), atom(6, 'C1', 'LIG', 'A', 500, 0),
  atom(7, 'H1', 'LIG', 'A', 500, 10, 'H'), atom(8, 'C2', 'LIG', 'A', 500, 10, 'C', 0),
  atom(9, 'C1', 'LIG', 'A', 500, 20, 'C', 1, 'B'), 'END',
].join('\n'), '1abc').run();
const trajectory = await trajectoryFromPDB(parsed.result).run();
const model = trajectory.representative, h = model.atomicHierarchy;
const chain = h.chains.label_asym_id.value(0);
const structure = Structure.ofModel(model);

test('workspace revisions and references are checked before replacing the current view', () => {
  const w = {version:1,id:'workspace-1',revision:2,scenes:[{id:'scene-1',structures:[{id:'protein'}],layers:[{id:'site',structure_id:'protein',kind:'component'}]}]};
  assert.equal(validateEnvelope(w),w);
  assert.throws(() => validateEnvelope({...w,version:2}));
  assert.throws(() => validateEnvelope({...w,scenes:[{...w.scenes[0],layers:[{id:'bad',structure_id:'missing',kind:'component'}]}]}));
  assert.throws(() => validateEnvelope({...w,scenes:[{...w.scenes[0],layers:[{id:'old',structure_id:'protein',kind:'binding_site'}]}]}));
  assert.throws(() => checkRevision(w,{...w,revision:1}),/Stale/);
  assert.throws(() => checkRevision(w,{...w,title:'different'}),/Conflicting/);
  assert.doesNotThrow(() => checkRevision(w,{...w,revision:3}));
  assert.doesNotThrow(() => checkRevision(w,{...w,id:'another',revision:0}));
});


test('Builder scenes expose coordinate-derived ligand and residue pickers through the same viewer', () => {
  const inventory = coordinateInventory(structure);
  assert(inventory.ligands.some(l => l.comp_id === 'LIG' && l.auth_seq_id === 500));
  assert(inventory.chains.some(c => c.label_asym_id === chain && c.residues.some(r => r.auth_seq_id === 101)));
  const root = {kind:'root',children:[{kind:'structure',ref:'protein',children:[{kind:'transform'},{kind:'component'},{kind:'component'}]}]};
  attachLayerRefs(root,[{id:'cartoon',structure_id:'protein',kind:'component',visible:true},{id:'hidden',structure_id:'protein',kind:'component',visible:false},{id:'ligand',structure_id:'protein',kind:'component',visible:true}]);
  assert.equal(root.children[0].children[1].ref,'cartoon');
  assert.equal(root.children[0].children[2].ref,'ligand');
});

test('provider coverage counts unique listed chain residues, retains raw values, and groups repeated labels', async () => {
  const { annotationGroups, uniqueAnnotations } = await import('../src/workspace-annotations.ts');
  const feature = (id, start, end, value, chain = 'A') => ({ id, kind: 'annotations', source: 'p2rank', accession: '', name: 'p2rank', description: '', source_url: 'https://example.test/provider', segments: [{ label_asym_id: chain, start, end, details: { raw: value } }] });
  const annotations = [feature('a',1,2,0.2), feature('b',2,3,0.9), feature('duplicate',1,2,0.2), feature('other',1,100,1,'B')];
  const scene = { structures: [{id:'ref',pdb_id:'2dn2',chains:[{label_asym_id:'A',residues:[{label_seq_id:1},{label_seq_id:2},{label_seq_id:3},{label_seq_id:5}]}],annotations}], layers: [] };
  const group = annotationGroups(scene).find(group => group.chainId === 'A');
  assert.equal(group.provider,'p2rank'); assert.equal(group.total,4); assert.equal(group.covered,3); assert.equal(group.percent,75);
  assert.equal(group.features.length,2); assert.deepEqual(group.features.map(f => f.segments[0].details.raw),[0.2,0.9]);
  assert.equal(uniqueAnnotations(annotations).length,3);
  assert.equal(annotationGroups(scene).find(group => group.chainId === 'B').percent,null);
});

test('optional data enriches a comparison without changing transforms, IDs, correspondence or unrelated layers', async () => {
  const { mergeOptionalScene } = await import('../src/workspace-annotations.ts');
  const base = {id:'aligned',title:'Aligned',comparison:{pairs:[{uniprot_position:1}]},structures:[{id:'reference',pdb_id:'2dn2',options:{transform:{matrix:[1,2,3]}},ligands:[],chains:[{label_asym_id:'A'}]}],layers:[{id:'protein',structure_id:'reference',kind:'component',visible:true,name:'Protein',sources:[]}]};
  const supplied = {structures:[{id:'foreign',pdb_id:'2dn2',ligands:[{comp_id:'HEM',label_asym_id:'C',auth_seq_id:1}],data_status:{ligands:'loaded'},data_sources:['https://example.test/ligands']}],layers:[{id:'ligand-1',structure_id:'foreign',category:'ligand',name:'HEM',kind:'component',visible:true,sources:[],component:{selector:{label_asym_id:'C'}}}]};
  const updated = mergeOptionalScene(base,[{structureId:'reference',scene:supplied}],'ligands',true);
  assert.deepEqual(updated.comparison,base.comparison); assert.deepEqual(updated.structures[0].options,base.structures[0].options);
  assert.deepEqual(updated.structures[0].data_sources,['https://example.test/ligands']);
  assert.equal(updated.structures[0].id,'reference'); assert.equal(updated.layers[1].structure_id,'reference');
  assert.equal(updated.layers[1].visible,true); assert.equal(updated.structures[0].data_status.ligands,'loaded');
  assert.deepEqual(updated.layers[0],base.layers[0]); assert.equal(base.layers.length,1); assert.equal(base.structures[0].ligands.length,0);
  assert.throws(() => mergeOptionalScene(base,[{structureId:'reference',scene:{...supplied,structures:[{...supplied.structures[0],pdb_id:'1cbs'}]}}],'ligands',true),/intended structure/);
});


test('shared annotation IDs across chains never import empty selectors into a comparison', async () => {
  const { mergeOptionalScene, annotationGroups } = await import('../src/workspace-annotations.ts');
  const feature = { id:'shared', kind:'annotations', source:'provider', name:'Track', source_url:'https://example.test/track',
    segments:['A','B'].map(label_asym_id => ({label_asym_id,start:1,end:2,details:{raw:0.4}})) };
  const base = {id:'aligned',title:'Comparison',comparison:{pairs:[]},structures:[{id:'reference',pdb_id:'2dn2',
    options:{transform:{matrix:[1,2,3]}},chains:[{label_asym_id:'A',residues:[{label_seq_id:1},{label_seq_id:2}]}],ligands:[]}],layers:[]};
  const supplied = {structures:[{id:'foreign',pdb_id:'2dn2',annotations:[feature],ligands:[],data_status:{annotations:'loaded'}}],
    layers:['A','B'].map((chain,index) => ({id:`annotation-${index+1}`,structure_id:'foreign',name:chain,kind:'component',
      category:'source_annotation',source_annotation_ids:['shared'],sources:['https://example.test/track'],
      component:{selector:[{label_asym_id:chain,beg_label_seq_id:1,end_label_seq_id:2}]}}))};
  const before = structuredClone(supplied);
  const result = mergeOptionalScene(base,[{structureId:'reference',scene:supplied}],'annotations',true);
  assert.equal(result.layers.length,1);
  assert.deepEqual(result.layers[0].component.selector,[{label_asym_id:'A',beg_label_seq_id:1,end_label_seq_id:2}]);
  assert.deepEqual(result.structures[0].annotations[0].segments,[feature.segments[0]]);
  assert.deepEqual(result.structures[0].options,base.structures[0].options);
  assert.deepEqual(result.comparison,base.comparison);
  assert.deepEqual(result.layers[0].sources,['https://example.test/track']);
  assert.equal(annotationGroups(result)[0].percent,100);
  assert.deepEqual(supplied,before);
  assert.deepEqual(base.layers,[]);
  const hidden = mergeOptionalScene(result,[],'annotations',false);
  assert.equal(hidden.layers[0].visible,false);
  assert.equal(mergeOptionalScene(hidden,[],'annotations',true).layers[0].visible,true);
  const otherChainOnly = {...supplied,layers:[supplied.layers[1]]};
  assert.equal(mergeOptionalScene(base,[{structureId:'reference',scene:otherChainOnly}],'annotations',true).layers.length,0);
});


test('Ligand-labelled tracks stay out of residue annotations while actual molecules have independent labels and visibility', async () => {
  const { annotationGroups, isLigandAnnotationLayer, ligandLayerLabel, mergeOptionalScene } = await import('../src/workspace-annotations.ts');
  const annotation = (id, source) => ({id,source,name:source,segments:[{label_asym_id:'A',start:1,end:2,details:{raw:0.5}}]});
  const scene = {id:'scene',structures:[{id:'entry',pdb_id:'1tqn',ligands:[{comp_id:'HEM',label_asym_id:'B',auth_asym_id:'A',auth_seq_id:501,insertion_code:'C'}],
    chains:[{label_asym_id:'A',residues:[{label_seq_id:1},{label_seq_id:2}]}],annotations:[annotation('ligand','Ligand'),annotation('p2rank','p2rank'),annotation('uniprot','UniProt')]}],
    layers:[{id:'annotation-1',structure_id:'entry',name:'Ligand',category:'source_annotation',source_annotation_ids:['ligand'],visible:false},
      {id:'annotation-2',structure_id:'entry',name:'p2rank',category:'source_annotation',source_annotation_ids:['p2rank'],visible:false},
      {id:'ligand-1',structure_id:'entry',name:'HEM',category:'ligand',visible:false,component:{selector:{label_asym_id:'B',auth_seq_id:501,pdbx_PDB_ins_code:'C',label_comp_id:'HEM'}}}]};
  const before = structuredClone(scene);
  assert.deepEqual(annotationGroups(scene).map(group=>group.provider),['UniProt','p2rank']);
  assert.equal(isLigandAnnotationLayer(scene,scene.layers[0]),true);
  assert.equal(isLigandAnnotationLayer(scene,scene.layers[2]),false);
  assert.equal(ligandLayerLabel(scene,scene.layers[2]),'1TQN · HEM · label chain B / author A · residue 501C');
  const annotated = mergeOptionalScene(scene,[],'annotations',true);
  assert.equal(annotated.layers[0].visible,false); assert.equal(annotated.layers[1].visible,true); assert.equal(annotated.layers[2].visible,false);
  assert.deepEqual(annotated.structures[0].annotations,scene.structures[0].annotations);
  const withLigands = mergeOptionalScene(annotated,[],'ligands',true);
  assert.equal(withLigands.layers[2].visible,true); assert.equal(withLigands.layers[0].visible,false);
  assert.deepEqual(scene,before);
});
