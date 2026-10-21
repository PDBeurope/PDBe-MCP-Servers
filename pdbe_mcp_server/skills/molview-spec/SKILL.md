---
name: molview-spec
description: Build or replace custom molecular views and guided molecular stories with PDBe evidence and MolViewSpec. Use for explicit visualization, representation, coloring, highlighting, or story requests.
metadata:
  version: "4"
---

# Molecular views and stories

Use the advertised `ebi-pdbe-build_mvs` tool for custom single scenes and
`ebi-pdbe-build_mvs_story` for a guided story. Use their advertised legacy aliases
only on servers that expose those names. Ordinary structure exploration uses
`ebi-pdbe-open_structure`; aligned comparison uses `ebi-pdbe-compare_structures`.
A successful explorer result (`status: "prepared"`) completes that viewing
request. Stop calling visualization tools; do not repeatedly reopen the entry
or switch to another viewer tool to wait for browser rendering.

Ground biological claims, residue mappings, ligand instances and scene choices
in PDBe evidence. Read [scene guidance](references/scenes.md) when building or
modifying a scene, and [story guidance](references/stories.md) for a tour or story.
The tool schemas are authoritative; full schema resources are available at
[scene schema](references/scene.schema.json) and [story schema](references/story.schema.json)
when exact field details are needed. Read the [builder API reference](references/builder-api.md)
for transforms, instances, additional structures, primitives, annotation tables
and serialized MolQL. The same operations work inside each story scene.

For a follow-up such as “add surface to the ligands”, recover the latest complete
builder from conversation or host scene context, preserve the entry and existing
components, add the requested ligand surface, and **call the builder tool again**.
For “add”, preserve existing representations unless the user asks to replace them.
If the prior viewer was the ordinary explorer, create a custom scene for that
same entry. Each call compiles a complete replacement. The host routes it according to
`pdbe_visualization_request.mode`: `replace_in_place` updates the originating
viewer, while `new_viewer` opens a separate viewer below the new chat response.
For a viewer edit, use the supplied context for that exact viewer, even if a
newer viewer exists elsewhere in the conversation. Do not pass host routing
fields to the builder tools.
If the entry or scene is unavailable, retrieve the missing context before building.

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
