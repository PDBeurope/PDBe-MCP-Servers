---
name: molview-spec
description: Build or replace custom molecular views and guided molecular stories with PDBe evidence and MolViewSpec, or explore PDBe-reported ligand interactions in the Molecular Workspace. Use for explicit visualization, representation, coloring, highlighting, ligand-contact, or story requests.
metadata:
  version: "6"
---

# Molecular views and stories

Use the advertised `ebi-pdbe-build_mvs` tool for custom single scenes and
`ebi-pdbe-build_mvs_story` for a guided story. Use their advertised legacy aliases
only on servers that expose those names. Ordinary structure exploration uses
`ebi-pdbe-open_structure`; aligned comparison uses `ebi-pdbe-compare_structures`.
A successful explorer result (`status: "prepared"`) completes that viewing
request. Stop calling visualization tools; do not repeatedly reopen the entry
or switch to another viewer tool to wait for browser rendering.

The App displays supplied scientific data. Preserve PDBe/SIFTS residue
correspondence and supplied alignment transforms. Do not calculate RMSD,
per-residue displacement, distance-cutoff ligand neighbourhoods or inferred
binding sites. Highlight binding-site residues only from explicit source
annotations with provenance; if absent, report the annotation as unavailable.
Coordinate loading and camera navigation do not establish new scientific results.

Ground biological claims, residue mappings, ligand instances and scene choices
in PDBe evidence. Read [scene guidance](references/scenes.md) when building or
modifying a scene, and [story guidance](references/stories.md) for a tour or story.
The tool schemas are authoritative; full schema resources are available at
[scene schema](references/scene.schema.json) and [story schema](references/story.schema.json)
when exact field details are needed. Read the [builder API reference](references/builder-api.md)
for transforms, instances, additional structures, primitives, annotation tables
and serialized MolQL. The same operations work inside each story scene.

On servers advertising `ebi-pdbe-update_workspace`, recover the latest complete
workspace for the exact target viewer from App context or structured tool output.
For follow-up changes, call that tool with the workspace, its revision as
`expected_revision`, and a suitable operation batch. Preserve unrelated layers,
structures, source annotations and transforms. Upserts replace complete named
definitions. Use only component/annotation layers with explicit data selections;
calculated `binding_site` layers and cutoff fields are unsupported. Use the
source PDBe/SIFTS residue correspondence table and export without adding geometric
measurements. A shared resource URI alone does not route results to an existing
viewer: the host must match the target workspace ID.

On older servers without workspace updates, recover the complete builder and
use the established full-replacement builder workflow. Do not pass host routing
fields such as `pdbe_visualization_request.mode` to PDBe tools. If the requested
viewer state is unavailable, recover it before constructing the edit.

## Ligand interaction workflow

Use `ebi-pdbe-ligand-interactions` for the Ligand & Binding Site Explorer workflow
inside the Molecular Workspace. Start with a PDB ID to list modeled ligand instances;
select an exact instance by CCD, author chain, author residue number, and insertion
code. Retain its label-chain and label-residue mapping for the viewer. Interaction
requests use the endpoint's demonstrated author chain and author residue identifiers;
never substitute label identifiers for these request fields.

Display one table row for each returned PDBe interaction record. Preserve atom lists,
multi-atom groups, every supplied classification (including clashes and overlaps),
source labels, and supplied distances. Filters only hide returned rows; a maximum
distance filter does not detect contacts or define a binding site. Keep each source
interaction record type visible. Apply a maximum-distance filter only when the current
records share one interaction geometry type; when types are mixed, leave all rows
visible until the user narrows the type. Do not recalculate distances, infer contacts,
reclassify records, or score interaction importance.
Distinguish distributed computational interaction classifications from curated
functional annotations. Treat conservation, validation, binding-site and functional
annotations as supporting evidence, with source and retrieval provenance; report
missing values as unavailable.

Contact lines require unambiguous atom identifiers plus coordinate model and assembly
context. If source records do not resolve those identifiers to exactly one coordinate
copy, leave the table available and do not draw a line. Preserve the selected ligand,
filters, and source records as restorable workflow state. CSV export must retain
original identifiers, atom groups, interaction type, all classifications, source
distance and provenance.

Only report that a replacement or story was created after a successful tool
result in the current turn. A prose description or a skill-reference read does
not create a visualization. On a validation failure, correct the reported fields and retry once with a
changed specification. Never repeat identical failed input. If that retry fails,
stop and state that the view was not created. Network/runtime failures do not
justify speculative specification changes. The App reports coordinate loading
separately, so compilation alone does not establish successful rendering.

A result with `status: "compiled"` completes construction: **stop calling builders**
and summarize the result. The full MVSJ is intentionally delivered in the App
artifact; model-facing text/structuredContent contains the normalized replacement
specification. That specification is not a placeholder. Pending browser loading
or the absence of the full MVSJ in the model-visible text is not a build failure.
Do not rebuild to wait for the viewer or obtain raw MVSJ unless the user requests
the exported data.

Return concise prose with the structural point and any material limitation.
The host renders the App; do not paste MVS JSON, executable builder code, or App
HTML into chat unless the user specifically requests the data or an example.
