# Molecular Workspace MCP App

[Project README](../README.md)


Structure Explorer, Structure Comparison, and MolViewSpec Builder now open the
same molecular workspace at `ui://pdbe/molecular-workspace`. A workspace can
combine protein chains, ligand instances, binding-site residues, annotations,
alignments, density, and molecular stories in one Mol* 5.13.1 viewer.
The existing tool names remain available; their results use the same workspace
contract and renderer. Non-UI clients retain text and structured data fallbacks.

The interface uses TypeScript, HTML, CSS, the official MCP Apps browser SDK,
and the native Mol* viewer. Its React integration preserves Mol*'s native
story captions and snapshot navigation.

Build the UI with Node.js 22.12+ before starting the server or building a Python
distribution:

```bash
cd apps/structure-explorer
npm ci
npm run build
cd ../..
uv sync
```

The build creates `pdbe_mcp_server/ui/workspace.html` and identical compatibility
artifacts named `structure-explorer.html`, `structure-comparison.html`, and
`mvs-viewer.html`, including the viewer, styles, SDK,
and third-party license notices. Python wheels and source
distributions include these artifacts when built. Rebuild them after UI
changes; publishing a Python package requires this build step.

For a local stdio connection, configure your MCP Apps client with:

```json
{
  "mcpServers": {
    "PDBe Structure Explorer": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/PDBe-MCP-Servers", "pdbe-mcp-server", "--server-type", "pdbe_apps_server"]
    }
  }
}
```

For Streamable HTTP, run `uv run pdbe-mcp-remote-server` and connect the client
to `http://127.0.0.1:8000/apps/`. With `--all`, the app tool and its UI resource
are also available at `/all/`. `ROOT_PREFIX` applies to both paths. For legacy
SSE, use `--server-type pdbe_apps_server --transport sse` on the stdio executable.

The model-visible tool is `pdbe_open_structure(pdb_id, assembly_id?, chain_id?)`.
`chain_id` is a **label chain ID** (`struct_asym_id`); the UI shows both author
and label identifiers. Omit `assembly_id` to view the deposited asymmetric unit.
The first coordinate model is loaded. Assembly views may omit entry chains or
show symmetry copies; list selections apply to all copies, while 3D clicks retain
the clicked instance. Residue lists come from deposited-entry PDBe annotations,
and unobserved residues cannot be highlighted. Non-polymer selections use author
residue numbers and insertion codes rather than PDBe's internal residue index.

Only public PDBe endpoints on `https://www.ebi.ac.uk` are needed for browser
network access. Their origin is declared in the UI resource CSP. The host needs
MCP Apps support, WebGL, and network access to that origin. The evidence panel
lists source endpoints and retrieval time. Missing optional annotations produce
a warning; coordinate failures offer a retry through **Open structure**.

Structure inspection, precomputed structure comparisons, and custom MVS scenes are available.

### Custom MolViewSpec scenes

`ebi-pdbe-build_mvs` builds and displays a custom molecular scene in the
MolViewSpec App (`ui://pdbe/mvs-viewer`). Supply a PDB entry and scene components,
such as a cartoon representation for the polymer and ball-and-stick for a ligand:

```json
{
  "version": 1,
  "builder": {
    "pdb_id": "1cbs",
    "title": "Protein and ligand",
    "components": [
      {"selector": "polymer", "representation": "cartoon"},
      {"selector": "ligand", "representation": "ball_and_stick", "focus": true}
    ]
  }
}
```

Scenes support common molecular representations, selection and styling options,
annotations, camera settings, and additional structures or primitives. The App
can restore and export scenes as MVSJ. See the `molview-spec` skill for supported
builder fields and examples.

### Molecular stories

`ebi-pdbe-build_mvs_story` creates a multi-scene molecular story in the same App.
Provide a title and an ordered set of scenes, each with its own scene definition.
Stories support playback, transitions, and MVSJ export.

### Remote molecular visualization skill

The Apps and aggregate servers provide the `molview-spec` skill and its reference
files as MCP resources. MCP clients can discover the skill and retrieve its
guidance when needed.

### Structure Comparison Workbench

`pdbe_compare_structures` opens `ui://pdbe/molecular-workspace` in MCP Apps
clients. For example, compare deoxyhaemoglobin and oxyhaemoglobin alpha chains:

```json
{
  "reference_pdb_id": "4hhb",
  "reference_chain_id": "A",
  "mobile_pdb_id": "1hho",
  "mobile_chain_id": "A"
}
```

Chain selectors use exact, case-sensitive **label chain IDs**. Both chains must
have a shared UniProt mapping and occur in the same PDBe superposition segment.
If several mappings or segments qualify, supply `uniprot_accession` or the
1-based `segment_index` reported in the error. Unsupported pairs return a clear
unavailable result.

The shared API executor retrieves chain metadata, the generated SIFTS mappings
tool, and the registered `/uniprot/superposition/{uniprot_accession}` operation.
The existing HTTP client retrieves PDBe's static matrix file at
`https://www.ebi.ac.uk/pdbe/static/superpose/matrices/{accession}`; this file is
outside the OpenAPI schema. Both source matrices are applied unchanged in Mol*.
There is no additional structural fitting or coordinate-processing dependency.

The shared viewer displays aligned chains, deposited ligand instances, and
optional source-provided annotation layers. Each ligand receives the same
supplied transform as its structure. Binding-site residues are displayed only
when explicitly supplied by an annotation source, retaining their provenance.
The app does not infer a neighbourhood from a distance cutoff.

The **Residue correspondence** table and CSV export retain PDBe/SIFTS-mapped
pairs, UniProt positions, label/author residue identities, insertion codes,
source transforms and provenance. Selecting a pair focuses its displayed
residues and makes the supplied correspondence available in MCP context.
Correspondence is a mapping between residues; it is separate from geometric
similarity measurements.

**Scientific values come from supplied data.** The app applies PDBe's
precomputed transforms and maps unambiguous, equal-length SIFTS segments to
residue identities. It does not calculate RMSD, per-residue displacement,
proximity-derived sites, or a new structural fit. Missing source annotations
remain unavailable; they are not replaced with inferred site definitions.
Coordinate metadata inspection and camera focus support viewing only.

### API reuse and annotations

The API MCP tools and Structure Explorer share the `OpenAPIToMCPGenerator`
executor. It resolves registered GET operations from the configured OpenAPI
schema and returns raw JSON with source and retrieval time. API tools format
that JSON as text or TOON; the app normalizes it directly. The HTTP server
shares one executor instance between `/api/`, `/apps/`, and `/all/`.
`enableMCP` controls model-visible tools; schema GET operations such as residue
listing can also be called internally by the app. This shares request handling
and schema loading, but does not cache API responses across calls.

For each polymer entity, the app retrieves domains, residue annotations,
binding sites, and UniProt mapping tracks through that executor. Annotations
become optional named workspace layers, initially hidden. Enable a layer to show
its mapped residues; Focus zooms to that layer. The residue browser preserves
label/author numbering and publishes annotation evidence for selected residues.

Track PDB indices map to label residue positions while preserving discontinuous
segments and chain scope. Binding-site segments carrying a bound molecule ID use
that instance's author chain. UniProt positions translate only through explicit,
equal-length SIFTS segments. Ambiguous or unmappable segments are omitted with a
warning; unavailable optional annotations do not prevent structure loading.
Mol* renders the supplied definitions without independent domain fetching.

### Workspace composition and updates

`pdbe_mcp_server/workspace.py` defines the versioned scientific state and the
adapters for Explorer, Comparison, and Builder. `workspace-renderer.ts` owns the
shared Mol* runtime; `workspace-capabilities.ts` reads coordinate metadata for selection and camera
navigation. It does not calculate scientific measurements or sites. All static scenes still compile through the
existing validated MVS builder, preserving its selection, transform, annotation,
primitive, density and story support.

A workspace contains a stable ID, revision, scenes, structure definitions,
visual layers, evidence sources, warnings, and saved camera/active-scene state.
A layer references a structure ID and contains a component or annotation definition. Coordinates are not embedded in saved state; the App loads them for rendering.
Residue mappings and source annotations are retained as supplied data.

`ebi-pdbe-update_workspace` accepts the latest complete `workspace`, an
`expected_revision`, and an ordered `operations` list. Supported operations are
`upsert_structure`, `remove_structure`, `upsert_layer`, `remove_layer`, and
`set_visibility`, `upsert_scene`, and `remove_scene`. Every operation names its `scene_id` and `target_id`.
Upserts supply a matching `scene`, `structure`, or `layer`; visibility supplies
`visible`. Scene upserts compose density, scene settings, comparison evidence and
additional story scenes through the same contract.
The entire batch validates before a new revision is returned. Removing a
structure removes dependent layers and its comparison. Replacing a structure
also invalidates its comparison so stale correspondence cannot be reused. An empty operations list validates
and restores a saved workspace without incrementing the revision.

The server is stateless: callers supply their base snapshot, and revision checks
compare against that snapshot. They are not a distributed lock or a guarantee
against concurrent writers. The App rejects older revisions and conflicting
scientific state at the same revision for its current workspace. Matching-ID updates retain the existing viewer and camera; layer
visibility persists in the workspace definitions. Explicit file restoration can
restore an older saved revision and its camera. Save workspace exports editable
JSON; Save MVSJ exports the compiled molecular visualization.

**Host routing:** sharing a resource URI does not by itself join separate App
instances. To update an existing viewer across model tool calls, the host must
route matching workspace IDs to that instance. Otherwise the returned complete
state opens as a new viewer. App-initiated layer changes use `callServerTool` and
apply its result to the originating viewer. No global process-wide workspace
store or cross-user session state is introduced.

Workspace restore and updates accept scientific definitions, not executable code
or arbitrary MVS trees. Coordinate and annotation URLs retain the existing
builder validation and resource CSP. The server returns `render_status=pending`;
loaded, empty and error states come from the App. Residue correspondence remains
available from supplied PDBe/SIFTS data and is not a calculated displacement.

Run the annotation mapping checks with:

```bash
uv run pytest tests/test_api_tools.py tests/test_apps.py tests/test_workspace.py -o addopts=''
cd apps/structure-explorer
npm test
```

