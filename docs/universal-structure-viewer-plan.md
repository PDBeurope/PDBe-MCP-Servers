# Universal Mol* Viewer: Migration Plan

**Status:** In progress in this repository; sibling-repository migrations remain planned  
**Scope:** This repository's Molecular Workspace, the `pdbe-chat` worktree, and
the `afdb-mcp-server` worktree

## Goal

Make this repository's Mol* MCP App a reusable structural viewer that can load
coordinates supplied by different MCP servers, including PDBe experimental
structures and AlphaFold DB predicted models. The structure provider supplies
the coordinate URL and format; the viewer renders the supplied structure and
does not assume PDBe metadata exists.

Keep provider-specific discovery and scientific guidance with the provider
server. In particular, AFDB guidance must explain how to choose the right model
and coordinate URL, and must distinguish predicted models from experimental
structures. The shared viewer should not discover models, synthesize URLs, or
infer scientific annotations.

## Proposed contract

Introduce a provider-neutral structure source alongside the existing PDBe entry
source. The conceptual source descriptor is:

```json
{
  "source": {
    "kind": "url",
    "coordinate_url": "https://coordinates.example.org/model.bcif",
    "format": "bcif",
    "model_id": "provider-specific-id",
    "title": "Human-readable model label",
    "source_name": "AlphaFold DB",
    "model_kind": "predicted"
  },
  "capabilities": {
    "sequence": true,
    "sequence_annotations": false,
    "ligands": false,
    "comparison": false
  }
}
```

This illustrates the boundary, not a final schema. Final field names and
format values should be agreed before implementation. The contract should:

- Make `coordinate_url` and an explicit supported coordinate `format` the
  minimum needed to render a remote model. Do not require a PDB accession.
- Preserve the provider's model ID, display title, source/provenance, and
  model kind as display metadata; these must not be used to guess a URL.
- Keep the current PDBe accession/assembly source as a supported adapter, so
  existing Explorer, Comparison, MVS Builder, and story workflows continue to
  work.
- Use the same provider-neutral source descriptor in ordinary opens, custom
  MVS scenes, and every story scene. A story scene may use a different
  registered source from another scene.
- Represent optional data as capabilities and optional payloads. Sequence
  availability is distinct from sequence annotations; a model may have a
  sequence track with no annotation tracks, or neither.
- Keep annotations source-backed and explicitly mapped to structure residues.
  Missing annotations mean “not supplied/unavailable,” not an empty inferred
  result.
- Reject unsupported formats clearly. “Universal” means any compatible
  structure source and supported format, not arbitrary binary data.

Provider-specific skills should teach the assistant how to obtain this
descriptor from that provider's own results. They should not add provider
branches to the shared viewer or put executable plugin code in skills.

## Security and URL policy

The App currently declares its network access through MCP App CSP metadata.
The current `connectDomains` list is PDBe/wwPDB-specific. Arbitrary
`coordinate_url` support must not be implemented by allowing every origin.

Before implementation, choose and document one of these controls:

1. **Configured origin registry (recommended):** each deployed viewer server
   explicitly configures the HTTPS origins it supports. Validate the submitted
   URL against this registry and include only configured origins in the App
   resource's `connectDomains`.
2. **Provider registration:** a provider adapter registers its coordinate
   origins and formats with the viewer server. A per-launch resource URI may
   select a registered provider/origin; resource handling must validate that
   selection and return matching CSP metadata.

Either way, reject non-HTTPS URLs, credentials, query parameters, fragments,
unsupported ports, malformed URLs, and unregistered origins. Do not use
wildcard origins as a shortcut.
Only coordinate loading should use the custom URL; annotations and other
resources remain separately sourced and capability-gated. If a future source
cannot be safely permitted in the host's CSP, use an explicitly designed
server-side retrieval/proxy policy rather than silently weakening CSP.

## This repository: implementation plan

### 1. Separate shared rendering from PDBe data preparation

- In `pdbe_mcp_server/workspace.py`, introduce a discriminated structure source
  for PDBe entry IDs versus provider-supplied coordinate URLs. Keep existing
  workspace validation, revision behavior, and serialized-workspace
  compatibility.
- Add a generic open-structure tool in `pdbe_mcp_server/apps.py` that accepts
  the validated source descriptor and optional capabilities/data. Keep
  `pdbe_open_structure` as the PDBe convenience entry point; adapt it to the
  shared workspace contract instead of removing its annotations, ligands, or
  assembly behavior.
- Ensure a generic URL-backed structure does not call PDBe APIs merely because
  it is rendered by this server. Keep API fetches, ligand tooling, comparison,
  and annotation loading behind PDBe-specific capability paths.

### 2. Teach the renderer to load coordinate URLs

- Update `apps/structure-explorer/src/workspace-renderer.ts` and the workspace
  compilation/loading boundary to support URL-backed coordinates with an
  explicit supported format. Reuse Mol*'s supported coordinate-loading path;
  do not convert a URL to a fabricated `pdb_id`.
- Keep camera, selection, workspace updates, and MVS/story rendering
  behavior working for existing PDBe scenes.
- For URL-backed sources, render basic Mol* controls and source/model metadata
  even when there are no PDBe layers or source annotations.

### 3. Generalize the MVS builder and molecular stories

- Extend the input contract in `pdbe_mcp_server/mvs.py` so a structure can be
  specified by either the existing PDBe entry fields or the provider-neutral
  coordinate source. Keep `pdb_id` as a backwards-compatible shorthand.
- Apply that source contract to all structures in a custom scene and to each
  scene in a molecular story; do not require every scene to be a PDB entry or
  silently reuse one scene's source in another.
- Verify the official MolViewSpec structure-source schema supports the
  required remote URL and format combinations. Compile valid MVS/MVSJ using
  supported source definitions; if a needed source is not expressible in the
  current MVS version, add a validated app-side adapter rather than accepting
  arbitrary MVS trees or inventing a PDB ID.
- Provide provider-neutral tool names such as `build_structure_scene` and
  `build_structure_story`, while retaining the current PDBe-prefixed names as
  compatibility aliases during migration. Tool descriptions and schemas must
  describe the source contract, not imply that all inputs are PDBe entries.
- Preserve the source/model label and provenance in the scene/story UI and
  exported workspace/MVSJ wherever the format permits. A story can combine
  sources, but must not imply alignment or biological correspondence unless
  supplied explicitly; no new fitting, RMSD, annotations, or other scientific
  results are inferred by the builder.
- Update `BuildMvsInput`, `BuildStoryInput`, workspace adapters, generated
  schema/reference files, and `molview-spec` skill guidance together so
  validation, model-facing instructions, and implementation stay aligned.

### 4. Make sequence and annotations optional

- In `apps/structure-explorer/src/workspace-main.ts` and `workspace.html`,
  make sequence UI conditional on an extractable polymer sequence and make
  annotation tracks conditional on actual supplied tracks.
- Do not present an empty annotation panel as if annotations were fetched.
  Show a concise unavailable/not-provided state only where useful.
- Preserve current Nightingale linking and annotation mapping for PDBe and
  ensure a URL-backed model without annotation data still loads and can be
  selected in 3D.
- Gate PDBe-only UI (comparison correspondence, deposited ligands,
  ligand-interaction workflow) on the relevant source capability rather than
  on assumptions about all structures.

### 5. Register the common App entry point safely

- Update App resource registration and CSP handling in
  `pdbe_mcp_server/apps.py` for the configured-origin policy above.
- Make the generic launch tool point to the common workspace resource. Keep
  existing resource/tool aliases during migration where clients depend on
  them; do not force `pdbe-chat` to depend on a new tool before it can discover
  it.
- Preserve the current bundle/build behavior in
  `apps/structure-explorer/package.json`, Vite configuration, and Python
  package data so the universal App ships in wheels and source distributions.
- Update `docs/molecular-workspace.md`, `README.md`, and
  `pdbe_mcp_server/skills/molview-spec/` to describe the generic source
  contract for ordinary opens, custom scenes, and stories separately from
  PDBe-only workflows.

### 6. Tests and migration gate

- Python tests: source descriptor validation, HTTPS/origin policy, CSP
  metadata, generic tool responses, PDBe compatibility, and no PDBe calls for
  URL-backed models. Cover generic MVS scene/story inputs, multiple structure
  sources, invalid per-scene sources, and legacy `pdb_id` inputs.
- UI tests: load a URL-backed fixture in at least one supported format; omit
  annotations without failing; display sequence only when available; retain
  PDBe annotation, comparison, story, and in-view update regression coverage. Verify
  generic stories preserve each scene's source metadata and do not claim
  unsupported alignment.
- Build/package checks: verify generated UI artifacts and confirm Python
  distributions include the same single-file App.
- Acceptance: existing PDBe opens, custom scenes, and stories remain
  compatible; an AFDB `.bcif` URL supplied by the caller loads in an ordinary
  view, a custom MVS scene, and a story without AFDB-specific logic in this
  repository; unsupported formats and disallowed origins fail with actionable
  errors.

## `pdbe-chat` plan

Target worktree: `/Users/sreenath/.thinkrail/worktrees/pdbe-chat/workspace-6`

The chat application should select a provider-specific visualization workflow,
then launch the common viewer with provider-returned coordinate information.
It should not make the PDBe viewer responsible for AFDB discovery or let a
predicted model pass through a PDB-ID route.

1. **Preserve source selection and evidence distinctions.** Keep the current
   PDBe, UniProt, and AFDB source-family rules. Keep experimental entries and
   predicted models distinct in answers, model metadata, and viewer labels.
   Never treat absence in one provider as absence in another.
2. **Update visualization routing.** Extend the open-structure request/model
   from only `pdb_id` to a validated source descriptor or provider-aware
   arguments. Update `backend/pdbe_chat/models.py`, the manager's
   `open_structure` selection in `backend/pdbe_chat/mcp.py`, the route in
   `backend/pdbe_chat/main.py`, and the frontend call in
   `frontend/src/app/app.component.ts`. Keep the existing PDBe shortcut and
   backward-compatible `pdb_id` behavior.
3. **Launch the shared App through discovery.** Resolve the common viewer tool
   from currently discovered MCP tools and its advertised `resourceUri`; do not
   hard-code a server namespace, assume a fixed alias, or launch the retired
   AFDB App. Pass the exact AFDB coordinate URL and explicit format returned by
   AFDB search metadata. Validate the launch payload against the common viewer
   tool's current schema.
 4. **Make visualization skills provider-aware.** Update the local
    `backend/skills/pdbe-domain/` and
    `backend/skills/afdb-protein-search/` guidance. Review the discovered
    PDBe `molview-spec` remote skill (or add a local equivalent only if the
    chat needs one). Make its custom-scene and story instructions accept the
    same provider-neutral structure source as ordinary opens. PDBe guidance
    should continue to use PDBe entry data for experimental structures. AFDB
    guidance should direct the assistant to retrieve `modelEntityId` and
    `bcifUrl` (or the source-supported equivalent), preserve the model's
    prediction label, then pass the returned URL/format to the common viewer,
    scene builder, or story builder. Do not convert non-PDB models into
    fabricated `pdb_id` values. Remove instructions that route AFDB structures
    to an AFDB-specific App or prohibit the shared generic viewer.
5. **Update the operator policy, not just the skills.** In
   `backend/AGENTS.md`, replace App-specific assumptions with rules to use the
   matching provider skill, pass source-returned URLs rather than constructing
   URLs, respect viewer capabilities/CSP failures, and preserve
   experimental-versus-predicted distinctions. Skills remain untrusted
   reference guidance and cannot override these guardrails.
 6. **Update app context and UI tests.** Ensure
    `frontend/src/app/shared/mcp-scene-context.ts` and related result handling
    can retain source, model ID, URL, and format for follow-ups without
    reclassifying a model as PDBe. Preserve source metadata for custom scene
    and story requests as well as ordinary opens. Update route/model/API tests
    for both providers, URL validation, multi-source stories, wrong-source
    rejection, and unavailable common viewer cases.
7. **Skill approvals/configuration.** Review
   `backend/remote-skills-approved.json` and server configs after the AFDB
   server retires its remote skill. Keep or replace that approved workflow with
   an application-owned AFDB skill only if the chat's existing policy calls for
   it; remove stale approval metadata for the retired server skill.

The `pdbe-chat` worktree already contains local modifications, including
AFDB-related guardrail/skill changes. Treat those as user work: review and
merge the plan into them rather than overwriting or reverting them.

## `afdb-mcp-server` plan

Target worktree: `/Users/sreenath/.thinkrail/worktrees/afdb-mcp-server/workspace-2`

Retain AFDB search, UniProt search, provider lookup, and the server's data
schemas. Retire its viewer and all server-published remote-skill support after
`pdbe-chat` has migrated to the common viewer and has replacement guidance.

1. Remove `register_apps` and its import/call from
   `afdb_mcp_server/main.py`; remove the `open_alphafold_structure` tool and
   `ui://afdb/structure-viewer` resource in `afdb_mcp_server/apps.py`.
2. Remove remote-skill protocol/catalog/middleware registration from
   `afdb_mcp_server/main.py`; then remove `afdb_mcp_server/skills.py`, the
   `afdb_mcp_server/skills/protein-search/` resource tree, and the associated
   skill-only middleware/extension code. Do not remove AFDB search or provider
   metadata tools.
3. Remove viewer and skill packaged-file entries from `pyproject.toml`; retire
   `apps/structure-viewer/`, generated UI assets, UI build instructions, and
   stale README sections. Check `Makefile`, Docker/package workflows, and lock
   files for UI or YAML-only dependencies before removal.
4. Remove or replace `tests/test_apps.py`, `tests/test_skills.py`, and
   `tests/test_skills_remote.py`. Retain coverage for AFDB/UniProt search,
   provider details, package data that remains, and server startup without App
   or Skills extensions.
5. Update `pdbe-chat` server config/approval files and validate that broad
   protein discovery still starts at UniProt, AFDB search still uses discovered
   collection schemas, and AFDB model URLs still come from returned metadata.

**Ordering:** first implement and deploy the common viewer; next migrate and
test `pdbe-chat`; only then remove AFDB App/remote-skill support. This avoids a
period where AFDB models are searchable but cannot be opened and their workflow
guidance has disappeared.

## Rollout and compatibility

1. Agree on the source descriptor, supported formats, and origin policy.
2. Add URL-backed rendering and optional capabilities while retaining existing
   PDBe interfaces.
3. Add the common viewer launch tool/resource and verify PDBe regression tests.
4. Migrate `pdbe-chat` and exercise PDBe and AFDB end-to-end with real,
   source-returned URLs.
5. Remove AFDB's viewer and remote skills after the chat cutover.
6. Remove compatibility aliases only in a separately announced breaking
   release, if they are no longer used.

Do not claim that a structure loaded merely because the server accepted or
compiled a URL. The App should report coordinate fetch/parse/render status
separately, and the chat should distinguish launch success from viewer load
failure.
