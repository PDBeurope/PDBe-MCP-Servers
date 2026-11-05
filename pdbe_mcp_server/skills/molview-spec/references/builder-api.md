# Structured MolViewSpec builder API

Use `ebi-pdbe-build_mvs` with `{"version": 1, "builder": {...}}` or put the
same builder inside each scene of `ebi-pdbe-build_mvs_story`. These are data
inputs: never send Python, JavaScript, arbitrary MVS nodes or shell commands.
The generated scene/story schemas are authoritative, including bounds and
representation-specific options. This reference describes the exposed methods
of the installed Python builder and the pinned Mol* 5.13.1 viewer.

## Operation mappings

| Builder operation | Structured input |
| --- | --- |
| `create_builder()` / `Root.get_state()` | Created and serialized by the tool |
| `Root.canvas()` / `Root.camera()` | `canvas`, `camera` |
| `Root.download().parse()` | `structure.url`, `structure.format` |
| `Parse.model_structure()` | `structure.type: "model"`, `model_index` |
| `Parse.assembly_structure()` | `structure.type: "assembly"`, optional `assembly_id` |
| `Parse.symmetry_structure()` | `structure.type: "symmetry"`, `ijk_min`, `ijk_max` |
| `Parse.symmetry_mates_structure()` | `structure.type: "symmetry_mates"`, `radius` |
| CIF block selection and reference | `structure.block_header`, `block_index`, `ref` |
| `Structure.transform()` | `structure.transform` |
| `Structure.instance()` | `structure.instances[]` |
| Additional download/parse/structure branches | `additional_structures[]` |
| `Structure.component()` | `components[].selector` |
| `Structure.component_from_uri()` / `component_from_source()` | `components[].annotation` |
| `Component.representation()` | `components[].representation` |
| `Representation.color()` / `opacity()` / `clip()` | `color` / `colors[]`, `representation.opacity`, `representation.clip` |
| `Representation.color_from_uri()` / `color_from_source()` | `components[].color_from[]` |
| `Component.label()` / `tooltip()` / `focus()` | `label`, `tooltip`, `focus` |
| `Structure.label_from_uri()` / `label_from_source()` | `labels_from[]` |
| `Structure.tooltip_from_uri()` / `tooltip_from_source()` | `tooltips_from[]` |
| `Structure.primitives()` and primitive methods | `primitives[]` |
| `Parse.volume().representation()` | `volumes[]` |
| Root focus / snapshot transition | `focus` / story scene `transition` |
| Native snapshots and global narrative | `story.scenes[]`, story title/description |

Inline `annotations[]` still accept selectors and component styling plus
optional `group_id`; this differs from `components[].annotation`, which selects
from an annotation table. Grouped inline labels require ordinary expression
selectors, not MolQL selectors.

For component and inline annotation transparency, write
`representation: {"type":"cartoon","opacity":0.3}`. Opacity is a number in
0–1. A misplaced component/annotation-level `opacity` is normalized to this
field before MCP validation, but conflicting nested/outer values fail explicitly.
The compiled MVSJ uses an opacity child node. Density `volumes[].opacity` is a
separate supported field and stays at the volume level.

## Transforms, instances and overlays

A transform accepts `rotation` (nine numbers, column-major proper rotation),
`translation` (three numbers), and optional `rotation_center` (three numbers or
`"centroid"`). Alternatively supply `matrix` (16 numbers, column-major affine
matrix), exclusively. `structure.instances[]` accepts the same fields. Supply
an explicit identity instance if the original copy should also be present.
Transforms do not calculate alignment: retrieve a valid alignment first.

`additional_structures` accepts up to nine complete structure layers alongside
the primary entry. Every layer has its own `pdb_id`, `structure`, components,
inline/table annotations, primitives, water setting, evidence sources and focus.
Canvas, camera, volumes, title and description belong to the enclosing scene.
Structure references are optional but must be unique within a scene.

Example layout (identities and transforms are illustrative, not biological evidence):

```json
{
  "pdb_id": "1cbs",
  "structure": {"ref": "primary"},
  "additional_structures": [{
    "pdb_id": "1cbs",
    "structure": {"ref": "copy", "transform": {"translation": [20, 0, 0]}},
    "components": [{"selector": "polymer", "color": "orange"}]
  }]
}
```

Coordinates still require HTTPS on `www.ebi.ac.uk`. Other coordinate origins,
standalone trajectories/topologies, shape-file loading and raw MVS trees are not
exposed. Adding a structure does not independently align it.

## Primitives and measurements

Each `primitives[]` item has a typed `type` and the fields below. Primitives are
attached to their layer's structure and can use coordinates or structure-based
positions. Geometry coordinates are in Angstroms. Do not invent coordinates for
a biologically meaningful feature: use evidence or expression-based positions.

| Type | Required geometry |
| --- | --- |
| `sphere` | `center`; optional positive `radius` (default 1) |
| `tube` | `start`, `end`; optional `radius`, `dash_length` |
| `arrow` | `start`, exactly one of `end` or nonzero `direction`; optional `length` and cap/tube settings |
| `distance` | `start`, `end`; optional tube settings, `label_template`, `label_size`, `label_color` |
| `angle` | `a`, `b`, `c`; optional label settings, `show_vector`, `show_section` |
| `label` | `position`, `text`; optional `label_size`, `label_color`, `label_offset` |
| `ellipse` | `center`, nonparallel `major_axis` and `minor_axis`; optional radii, angular limits and `as_circle` |
| `ellipsoid` | `center`, positive `radius` (one number or three); optional nonparallel axes |
| `box` | `center`, positive `extent` (three half-lengths); optional face/edge/wireframe styles |
| `mesh` | flat xyz `vertices`, triangle `indices`; optional color/tooltip/wireframe settings |
| `lines` | flat xyz `vertices`, pair `indices`; optional `color`, `tooltip`, `width` |

A position is `[x,y,z]`, a component expression such as
`{"label_asym_id":"A","label_seq_id":57}`, an expression union such as
`{"expressions":[{"label_asym_id":"A"}],"structure_ref":"primary"}`, or a
MolQL position `{"molql": {...}, "structure_ref":"primary"}`. Omit
`structure_ref` for the current layer; explicit references must name an existing
`structure.ref`. Measurements refer to positions/selection centers, so select
specific atoms when reporting an atom-to-atom distance.

```json
{"type":"distance","start":{"label_asym_id":"A","label_seq_id":57,"label_atom_id":"CA"},"end":{"label_asym_id":"A","label_seq_id":60,"label_atom_id":"CA"},"label_template":"Cα distance: {{distance}} Å"}
```

## Annotation tables

`components[].annotation` selects components from a table. Specify `schema`
(`whole_structure`, `entity`, `chain`, `auth_chain`, `residue`, `auth_residue`,
`residue_range`, `auth_residue_range`, `atom`, `auth_atom`, or `all_atomic`).
External tables require `uri` and `format: "json" | "cif" | "bcif"`. Embedded
coordinate tables require `category_name` and omit `uri`/`format`; the coordinate
format must be mmcif or bcif. Both accept `block_header`, `block_index`,
`field_name` and `field_remapping`.

Component tables additionally accept `field_values`, an array of component IDs;
omit it to include all annotation rows. Use either a component `selector` or an
`annotation`, never both. Normalized annotation components omit the default
selector so complete replacements can be submitted unchanged.

`components[].color_from[]`, `labels_from[]` and `tooltips_from[]` use the same
table descriptors, without `field_values`. Their default value columns are
respectively `color`, `label` and `tooltip`. Column values must follow the MVS
annotation schema; do not pass arbitrary API responses as tables. External
annotation URIs use the existing HTTPS ebi.ac.uk/wwpdb.org allowlist. The browser
loads these resources; compilation cannot prove availability or CORS permission.

```json
{"annotation":{"uri":"https://www.ebi.ac.uk/path/site.json","format":"json","schema":"residue","field_name":"component","field_values":["site"]},"representation":"ball_and_stick"}
```

## Serialized MolQL selectors

A component selector or color selector may be `{"molql": <application>}`.
Applications use `{"head":{"name":"symbol-name"},"args":{...}}` (named
arguments) or an `args` array (positional arguments). Leaf values are JSON
literals or known symbols. A selector's outer application must return an element
selection query. The compiler checks expression shape, known symbols, argument
names, required arguments, depth and node count. Mol* checks runtime semantics
and evaluates the query on the actual structure.

Read [pinned symbol signatures](molql-symbols.json) for exact names and arguments;
these are checked against the bundled viewer runtime. For example, this selects
a chain using a base-language query:

```json
{"molql":{"head":{"name":"structure-query.generator.atom-groups"},"args":{"chain-test":{"head":{"name":"core.rel.eq"},"args":[{"head":{"name":"structure-query.atom-property.macromolecular.label_asym_id"}},"A"]}}}}
```

Prefer ordinary expression selectors for straightforward identifiers. Use MolQL
for compound selections and spatial queries. Query/table selections may include
water; author those selections explicitly according to the user's water request.
PyMOL text and MolScript text are not accepted. They require transpilation before
calling this API; no transpiler is available in the installed Python release.

## Support boundary

The schema exposes the operations above for single scenes and story scenes.
It does not expose executable builder code, arbitrary custom nodes, general
animation/property interpolation, shape-file loading, standalone trajectories,
annotation palettes, or every optional primitive/group style from the package.
Use supported fields and state any material limitation. A compiled result proves
construction only; the App reports resource loading separately. Preserve the
complete normalized specification for follow-ups and stop after compilation.
The host determines placement: viewer edits use `replace_in_place` and main-chat
requests use `new_viewer`. Always compile through the same builder tools.
