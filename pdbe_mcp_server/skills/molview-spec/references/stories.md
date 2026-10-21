# Guided molecular stories

For a requested story, guided tour, or walkthrough, call
`ebi-pdbe-build_mvs_story` once with the complete story. Do not approximate it by
calling the single-scene tool repeatedly. Input:

```json
{
  "version": 1,
  "story": {
    "title": "Protein and ligand",
    "scenes": [
      {"id": "overview", "title": "Overview", "description": "The deposited structure.", "builder": {"pdb_id": "1cbs", "focus": true}},
      {"id": "ligand", "title": "Ligand context", "description": "The ligand selection is shown in detail.", "builder": {"pdb_id": "1cbs", "components": [{"selector": "polymer"}, {"selector": "ligand", "representation": "ball_and_stick", "focus": {"radius_factor": 1.5}}]}}
    ]
  }
}
```

This example illustrates the format, not evidence for biological claims. Verify
the relevant facts and mappings before using an entry or describing its function.

Use 2–20 ordered scenes with unique short IDs, titles, and concise descriptions.
Omitted IDs and titles become scene-1/Scene 1, scene-2/Scene 2, etc.; explicit
values are preferred. `linger_duration_ms` is accepted as an alias for duration_ms.
Each scene has a complete builder using the single-scene schema, so different
entries, assemblies, selectors, and viewpoints can appear in successive scenes.
For a translucent component, use
`{"selector":"polymer","representation":{"type":"cartoon","opacity":0.3}}`.
Opacity must be nested in `representation`, not directly on a component or
annotation. The same rule applies to every scene's complete builder.
Choose one structural point per scene and progress from overview to relevant
detail. A scene can contain up to ten coordinate sources using `additional_structures`;
provide evidence-backed transforms for aligned overlays. Use adjacent scenes
when a separate viewpoint or explanation is clearer.

Defaults are `duration_ms: 6500` and `transition_duration_ms: 1500`. Durations are
non-negative integers; zero is supported. The output is one native multiple-state
MVSJ with ordered snapshots and Mol* playback, not separate viewer artifacts.
Descriptions default to plain text; set `description_format: "markdown"` on the
story or individual scenes for Markdown. Mol* supplies narrative display,
scene navigation and playback. The App downloads the complete story.

For richer camera motion, set scene `transition` with `duration_ms`, `trajectory`
(linear, linear-relative, leap, leap-relative) and `easing` (linear or the supported
bounce/circle/cubic/exp/quad/sin in/out/in-out variants). This controls entry into
that snapshot and takes precedence over legacy snapshot transition timing.
Use explicit camera or focus settings to make the intended camera change visible.

For follow-up edits, retain the latest full story from host context, modify only
the relevant scene(s), and submit a complete replacement. To add surfaces to
ligands throughout a story, preserve all scene IDs, timing and narratives and
append a ligand surface component to each relevant scene. If the user refers to
one named scene, modify that scene. A replacement updates the originating viewer for host mode `replace_in_place`;
main-chat mode `new_viewer` creates a separate viewer.

## Optional kinase story pattern

For a story about ABL kinase, a useful arc is regulation by SH3/SH2, dysregulation,
active-state nucleotide context, targeted inhibition, resistance, and response
with another inhibitor. Choose only scenes supported by retrieved evidence and
adapt the arc to the user's requested depth. Candidate entries from the original
example are 1opl, 2gqg, 2g2i, 1iep, 3ik3 and 3oxz; verify identity, ligands,
conformation and relevance before using any of them. A narrative outline is not
evidence for BCR-ABL, T315I, imatinib or ponatinib claims. Use additional structures only for evidence-backed overlays, keep one structural
point per scene, and use concise titles
and descriptions. Never invent residues, contacts or mutations to fill a story.

If construction fails validation, correct the reported fields and retry once;
if it still fails, stop and report that no story was created. Do not repeat an
identical failing story or call the scene tool as an unrequested fallback.
After a compiled story result, stop building. Native snapshots are carried in
the App artifact even though the model sees only the normalized story spec.
