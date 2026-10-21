# Scene specifications

Call `ebi-pdbe-build_mvs` with `{"version": 1, "builder": {...}}`.
The builder requires `pdb_id`; it accepts legacy and extended accessions intact.
Do not include local-chat action fields such as `target`, `action`, or `type`.

The default is the first deposited model, a polymer cartoon, and no water.
Use `structure: {"type": "assembly", "assembly_id": "1"}` for a known assembly.
If assembly_id is omitted, Mol* chooses the first available assembly; do not invent an ID.
Coordinates default to PDBe BCIF. A custom coordinate URL must be HTTPS on
`www.ebi.ac.uk`, matching the viewer's network policy.

Components have a `selector`, `representation`, optional `color`/`colors`, `label`,
`tooltip`, and `focus`. Representations are cartoon, ball_and_stick, surface,
spacefill, carbohydrate, backbone, line, and putty. Opacity belongs inside
`representation`, between 0 (transparent) and 1 (opaque):
`{"selector":"polymer","representation":{"type":"cartoon","opacity":0.3}}`.
Do not put `opacity` beside `selector`, including in story scenes or inline
annotations. For transparency, expand a representation name into this object.
The compiler emits an opacity child node; it is not a raw MVS representation parameter.
Use colors such as `{"color": "#2787b5"}` and labels such as `{"text": "Ligands"}`.
Broad labels appear in the legend; residue labels or `scene: true` also appear in 3D.
Use tooltips for detailed evidence to avoid label clutter.

Resolve author residue numbering to label numbering for polymer selections:
`{"label_asym_id": "A", "label_seq_id": 57}`. A range uses `beg_label_seq_id` and
`end_label_seq_id`; an array of expressions selects their union. Keep chain IDs
case-sensitive. For a ligand instance, use its label chain, author residue ID,
and insertion code when applicable; non-polymer label sequence IDs are undefined.
`instance_id` identifies a particular assembly or crystal copy.

Inline `annotations` accept component fields plus `group_id`. Related records
with one label text and expression selectors can share a group label while
keeping individual colors and tooltips. Every annotation with `group_id` must
provide `label` with the same text as the other records in that group, and use
an expression selector (or an array of expressions). For example:
`{"selector": {"label_asym_id": "A", "label_seq_id": 57}, "group_id": "site", "label": "Binding site"}`.
For coloring or tooltips without a shared 3D label, omit `group_id`; labels are
then optional. On validation failure, correct the reported annotation field
before the single retry. Record evidence URLs in `sources`.
Explicit water selections require `include_water: true`.

To add ligand surfaces to an existing view, append a component:

```json
{"selector": "ligand", "representation": {"type": "surface", "opacity": 0.5}, "label": {"text": "Ligand surface"}}
```

Preserve the prior polymer, ligand sticks, colors, assembly and focus choices
unless they conflict with the user's requested change. Surface is supported;
there is no reason to fall back to the local builder for this request.
Representations accept `size_factor`. Cartoon accepts `tubular_helices`; putty
accepts `size_theme: "uniform" | "uncertainty"`; surface accepts `surface_type:
"molecular" | "gaussian"`. Ball-and-stick, line, spacefill and surface accept
`ignore_hydrogens`. Parameters must apply to the chosen representation.

`representation.clip` accepts one clipping region or an array. Plane uses
`point` and nonzero `normal`; sphere uses `center` and positive `radius`; box uses
`center` and positive `size`. All support `invert` and `variant: "pixel" | "object"`.
Opacity and clipping compile to child nodes, not representation parameters.

For requested density, add `volumes` with an evidence-supplied HTTPS `url`, optional
`channel_id`, `format` (map by default; bcif/mmcif/dx/dxbin also supported),
`representation: {"relative_isovalue": 1.0}`, optional `color` and `opacity`.
Use only one of `relative_isovalue` and `absolute_isovalue`; `show_faces` and
`show_wireframe` control the mesh. URLs must be on ebi.ac.uk or wwpdb.org, matching
App CSP. Retrieve actual density URLs and channel identifiers; do not invent them.

Custom structure formats include bcif/mmcif/pdb/pdbqt/gro/xyz/mol/sdf/mol2/lammpstrj.
A custom URL is required except for default PDBe BCIF. Coordinate sources remain
restricted to https://www.ebi.ac.uk. PQR, standalone trajectories/topologies and
shape files are not structure sources supported by this viewer workflow.
Typed primitives, structure transforms and instances, additional structures,
annotation tables and serialized MolQL selectors are supported; consult
[builder API reference](builder-api.md) for exact mappings and examples. PyMOL
text still requires an unavailable transpiler; use expression selectors or a
serialized base MolQL query instead.

## Visual conventions

Use neutral `#91bfdb` for background polymers and orange `#f28e2b` for emphasized
ligands and ions. `ligand` and `ion` are distinct selectors: do not assume ligand
includes sulfate or other ions. Prefer ball-and-stick for emphasis; use spacefill
when requested. Keep water hidden unless requested, then set `include_water: true`.
For evidence-backed validation overlays use severe/outlier `#d73027`, warning
`#fc8d59`, informational `#fee08b`. Label visible components with specific,
evidence-backed names and put category/source details in tooltips. Focus the
feature when it is the user's requested point; avoid cluttering overview scenes.
Scene descriptions accept `description_format: "plaintext" | "markdown"`.


## Input normalization and recovery

Prefer the canonical schema. Compatibility input accepts `pdbId`, `entry_id` or
`entryId` as `pdb_id` (also inside `structure`), `color: {"value": "blue"}` as
`color: {"color": "blue"}`, case-insensitive representation/static selector
names, `show_water` as `include_water`, and singular `component` as `components`.
A recognizable PDBe coordinate filename can supply a missing entry ID. Empty
components use the default polymer view. Conflicting aliases are errors, not
instructions to silently pick one. Unknown fields, invalid geometry and
unsupported representations still fail; do not substitute cartoon for an
unknown representation. Input normalization runs before MCP schema validation.

As compatibility recovery, component/annotation-level `opacity` is moved into
`representation.opacity`, including inside stories and additional structures.
An omitted representation retains the cartoon default; a representation string
is expanded to an object. Matching duplicate values are accepted, conflicting
values are rejected, and out-of-range/nonfinite values remain errors. Prefer the
canonical nested field; this recovery does not allow other unknown properties.

On a validation error, change the reported invalid fields and retry once. Never
repeat the same failing input, and stop after a compiled result. The full MVSJ
is attached to the App; its normalized specification in the model response is
not placeholder data. Coordinate retrieval happens in the browser and must not
be polled by repeated build calls.
