"""MCP Apps resources and scientific data for the Structure Explorer."""

import asyncio
import json
import re
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import mcp.types as types
import requests
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from pydantic import AnyUrl, ValidationError

from pdbe_mcp_server.api_tools import OpenAPIToMCPGenerator, get_shared_api_generator
from pdbe_mcp_server.comparison_tools import (
    comparison_data,
    comparison_input_schema,
    comparison_text,
)
from pdbe_mcp_server.execution import run_blocking_tool, tool_deadline
from pdbe_mcp_server.mvs import (
    BuildMvsInput,
    BuildStoryInput,
    build_mvs,
    build_mvs_story,
)
from pdbe_mcp_server.skills import SkillCatalog, add_skill_result_metadata
from pdbe_mcp_server.tool_names import PDBeServer
from pdbe_mcp_server.workspace import (
    UpdateWorkspaceInput,
    compile_workspace,
    update_workspace,
    workspace_from_comparison,
    workspace_from_mvs,
    workspace_from_structure,
)

WORKSPACE_RESOURCE_URI = "ui://pdbe/molecular-workspace"
RESOURCE_URI = "ui://pdbe/structure-explorer"
COMPARISON_RESOURCE_URI = "ui://pdbe/structure-comparison"
MVS_RESOURCE_URI = "ui://pdbe/mvs-viewer"
APP_MIME_TYPE = "text/html;profile=mcp-app"
UI_FILE = Path(__file__).parent / "ui" / "structure-explorer.html"
COMPARISON_UI_FILE = UI_FILE.with_name("structure-comparison.html")
MVS_UI_FILE = UI_FILE.with_name("mvs-viewer.html")
APP_RESOURCES = {
    WORKSPACE_RESOURCE_URI: "PDBe Molecular Workspace",
    RESOURCE_URI: "PDBe Structure Explorer",
    COMPARISON_RESOURCE_URI: "PDBe Structure Comparison Workbench",
    MVS_RESOURCE_URI: "PDBe Custom Molecular View",
}


@dataclass(frozen=True)
class AppDisplayOptions:
    """Presentation preferences, isolated to a request or resource URI."""

    show_header: bool = True
    show_search: bool = True

    @classmethod
    def from_query(cls, query: Mapping[str, str]) -> "AppDisplayOptions":
        def boolean(name: str, default: bool) -> bool:
            value = query.get(name)
            if value is None:
                return default
            if value.lower() not in {"true", "false"}:
                raise ValueError(f"{name} must be true or false")
            return value.lower() == "true"

        visible = not boolean("internal", False)
        return cls(boolean("show_header", visible), boolean("show_search", visible))

    def resource_uri(self, base_uri: str) -> str:
        if self == AppDisplayOptions():
            return base_uri
        return (
            base_uri
            + "?"
            + urlencode(
                {
                    "show_header": str(self.show_header).lower(),
                    "show_search": str(self.show_search).lower(),
                }
            )
        )


app_display_defaults: ContextVar[AppDisplayOptions] = ContextVar(
    "app_display_defaults", default=AppDisplayOptions()
)


def app_resource_base_uri(uri: str) -> str | None:
    """Identify app resources, including their display-specific variants."""
    parts = urlsplit(uri)
    base = urlunsplit(parts._replace(query="", fragment=""))
    return base if base in APP_RESOURCES and not parts.fragment else None


def request_display_options(server: Server) -> AppDisplayOptions:
    """Read HTTP preferences; stdio and direct handler calls use full UI."""
    try:
        request = server.request_context.request
    except LookupError:
        request = None
    return (
        AppDisplayOptions.from_query(request.query_params)
        if request
        else app_display_defaults.get()
    )


def normalize_annotations(
    payloads: list[tuple[str, str, Any, str]],
    chains: list[dict[str, Any]],
    ligands: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    """Map v2 feature tracks to explicit label-chain and label-residue segments.

    PDB track indices refer to the entity sequence, not author numbering.
    UniProt positions are translated only through an explicit equal-length SIFTS
    segment. Unsupported or ambiguous coordinates are reported and omitted.
    """
    features: dict[tuple[str, ...], dict[str, Any]] = {}
    mappings = {
        entity: data.get("data", [])
        for kind, entity, data, _ in payloads
        if kind == "uniprot_mapping" and isinstance(data, dict)
    }
    skipped = 0
    for kind, entity_id, payload, source_url in payloads:
        if not isinstance(payload, dict):
            continue
        for track in payload.get("data", []):
            extra = track.get("additionalData") or {}
            for region in track.get("residues", []):
                detail = region.get("additionalData") or {}
                chain_name = detail.get("bestChainId", extra.get("bestChainId"))
                bound_id = detail.get("boundMoleculeId")
                if bound_id:
                    bound = next(
                        (
                            ligand
                            for ligand in ligands
                            if ligand.get("bound_molecule_id") == bound_id
                        ),
                        None,
                    )
                    if bound is None:
                        skipped += 1
                        continue
                    chain_name = bound["auth_asym_id"]
                candidates = [
                    chain
                    for chain in chains
                    if chain["entity_id"] == entity_id
                    and chain["auth_asym_id"] == chain_name
                ]
                if len(candidates) != 1:
                    skipped += 1
                    continue
                chain = candidates[0]
                start, end = region.get("startIndex"), region.get("endIndex")
                if (
                    not isinstance(start, int)
                    or not isinstance(end, int)
                    or start > end
                ):
                    skipped += 1
                    continue
                index_type = str(region.get("indexType", "")).upper()
                if index_type in {"UNIPROT", "UNP"}:
                    accession = detail.get(
                        "uniprotAccession", extra.get("uniprotAccession")
                    )
                    translated: set[tuple[int, int]] = set()
                    for mapping in mappings.get(entity_id, []):
                        if accession and mapping.get("accession") != accession:
                            continue
                        if (
                            mapping.get("additionalData", {}).get("bestChainId")
                            != chain_name
                        ):
                            continue
                        for segment in mapping.get("residues", []):
                            ps, pe = segment.get("startIndex"), segment.get("endIndex")
                            us, ue = (
                                segment.get("unpStartIndex"),
                                segment.get("unpEndIndex"),
                            )
                            if all(isinstance(v, int) for v in [ps, pe, us, ue]):
                                if pe - ps == ue - us and us <= start <= end <= ue:
                                    translated.add((ps + start - us, ps + end - us))
                    if len(translated) != 1:
                        skipped += 1
                        continue
                    start, end = translated.pop()
                elif index_type != "PDB":
                    skipped += 1
                    continue
                known = {r["label_seq_id"] for r in chain["residues"]}
                if start not in known or end not in known:
                    skipped += 1
                    continue
                provider = str(track.get("dataType", kind))
                accession = str(detail.get("domainId", track.get("accession", "")))
                instance = str(detail.get("domain", detail.get("groupLabel", "")))
                name = str(detail.get("domainName", track.get("name", accession)))
                key = (kind, entity_id, provider, accession, instance, name, source_url)
                if key not in features:
                    features[key] = {
                        "id": f"feature-{len(features)}",
                        "kind": kind,
                        "source": provider,
                        "accession": accession,
                        "name": name,
                        "description": instance,
                        "source_url": source_url,
                        "entity_id": entity_id,
                        "segments": [],
                    }
                segment = {
                    "label_asym_id": chain["label_asym_id"],
                    "auth_asym_id": chain["auth_asym_id"],
                    "start": start,
                    "end": end,
                    "details": detail,
                    "original_index_type": index_type,
                    "original_start": region["startIndex"],
                    "original_end": region["endIndex"],
                }
                if segment not in features[key]["segments"]:
                    features[key]["segments"].append(segment)
    if skipped:
        warnings.append(
            f"Omitted {skipped} annotation segments with unsupported or ambiguous residue/chain mappings."
        )
    return list(features.values())


async def get_structure_data(
    arguments: dict[str, Any],
    generator: OpenAPIToMCPGenerator | None = None,
    include_annotations: bool = True,
    include_ligands: bool = True,
) -> dict[str, Any]:
    """Normalize entry metadata while preserving author and label identifiers."""
    pdb_id = str(arguments["pdb_id"]).lower()
    if not re.fullmatch(r"[1-9][a-z0-9]{3}", pdb_id):
        raise ValueError("pdb_id must be a four-character PDB accession, e.g. 4hhb")

    sources: list[str] = []
    warnings: list[str] = []
    if generator is None:
        generator = await run_blocking_tool(get_shared_api_generator)
    executor = generator
    operation_sources: dict[tuple[str, str | None], str] = {}
    semaphore = asyncio.Semaphore(4)

    async def fetch(
        endpoint: str, entity_id: str | None = None, optional: bool = False
    ) -> Any:
        path = f"/pdb/entry/{endpoint}/{{pdb_id}}"
        parameters: dict[str, Any] = {"pdb_id": pdb_id}
        if entity_id is not None:
            path += "/{entity_id}"
            parameters["entity_id"] = entity_id
        try:
            async with semaphore:
                result = await run_blocking_tool(
                    lambda: executor.execute_operation("GET", path, parameters)
                )
            data = result["data"][pdb_id]
            sources.append(result["source"])
            operation_sources[(endpoint, entity_id)] = result["source"]
            return data
        except (requests.RequestException, ValueError, KeyError) as error:
            if isinstance(error, requests.HTTPError) and error.response is not None:
                if error.response.status_code == 404 and endpoint == "ligand_monomers":
                    return []
            if not optional:
                raise ValueError(
                    f"Could not retrieve {endpoint} for {pdb_id.upper()} from PDBe. "
                    "Check the accession and try again."
                ) from None
            warnings.append(
                f"PDBe {endpoint} data is unavailable"
                + (f" for entity {entity_id}." if entity_id else ".")
            )
            return {} if endpoint == "residue_listing" else []

    summary, molecules = await asyncio.gather(fetch("summary"), fetch("molecules"))
    listing, ligand_records = await asyncio.gather(
        fetch("residue_listing", optional=True),
        fetch("ligand_monomers", optional=True)
        if (include_ligands or include_annotations)
        else asyncio.sleep(0, result=[]),
    )

    assemblies = summary[0].get("assemblies", [])
    assembly_id = arguments.get("assembly_id")
    if assembly_id and assembly_id not in {
        str(item["assembly_id"]) for item in assemblies
    }:
        raise ValueError(f"Assembly {assembly_id!r} is not listed for {pdb_id.upper()}")

    entities = {str(m["entity_id"]): m for m in molecules}
    chains = []
    for molecule in listing.get("molecules", []):
        entity_id = str(molecule["entity_id"])
        entity = entities.get(entity_id, {})
        for chain in molecule.get("chains", []):
            chains.append(
                {
                    "entity_id": entity_id,
                    "label_asym_id": chain["struct_asym_id"],
                    "auth_asym_id": chain["chain_id"],
                    "name": ", ".join(entity.get("molecule_name", [])),
                    "molecule_type": entity.get("molecule_type", "unknown"),
                    "residues": [
                        {
                            "label_seq_id": r["residue_number"],
                            "auth_seq_id": r.get("author_residue_number"),
                            "insertion_code": r.get("author_insertion_code", ""),
                            "comp_id": r["residue_name"],
                            "observed_ratio": r.get("observed_ratio"),
                        }
                        for r in chain.get("residues", [])
                    ],
                }
            )

    # Basic chain controls still work when the residue listing is unavailable.
    if not chains:
        for entity_id, entity in entities.items():
            for auth, label in zip(
                entity.get("in_chains", []), entity.get("in_struct_asyms", [])
            ):
                chains.append(
                    {
                        "entity_id": entity_id,
                        "label_asym_id": label,
                        "auth_asym_id": auth,
                        "name": ", ".join(entity.get("molecule_name", [])),
                        "molecule_type": entity.get("molecule_type", "unknown"),
                        "residues": [],
                    }
                )

    chain_id = arguments.get("chain_id")
    if chain_id and chain_id not in {c["label_asym_id"] for c in chains}:
        raise ValueError("chain_id must match a label chain ID (struct_asym_id)")

    ligands = [
        {
            "entity_id": str(ligand["entity_id"]),
            "label_asym_id": ligand["struct_asym_id"],
            "auth_asym_id": ligand["chain_id"],
            # Non-polymer label_seq_id is undefined in mmCIF. PDBe's
            # residue_number here is not a usable mmCIF label_seq_id.
            "label_seq_id": None,
            "auth_seq_id": ligand["author_residue_number"],
            "insertion_code": ligand.get("author_insertion_code", ""),
            "comp_id": ligand["chem_comp_id"],
            "name": ligand.get("chem_comp_name", ""),
            "bound_molecule_id": ligand.get("bm_id"),
        }
        for ligand in ligand_records
    ]
    entity_ids = [
        key
        for key, entity in entities.items()
        if entity.get("molecule_type") not in {"water", "bound"}
        and entity.get("sequence")
    ]
    tracks = ["domains", "annotations", "binding_sites", "uniprot_mapping"]
    jobs = (
        [(track, entity_id) for entity_id in entity_ids for track in tracks]
        if include_annotations
        else []
    )
    results = await asyncio.gather(
        *(fetch(track, entity_id, optional=True) for track, entity_id in jobs)
    )
    payloads = [
        (track, entity_id, data, operation_sources.get((track, entity_id), ""))
        for (track, entity_id), data in zip(jobs, results)
    ]
    annotations = normalize_annotations(payloads, chains, ligands, warnings)
    return {
        "pdb_id": pdb_id,
        "title": summary[0].get("title", pdb_id.upper()),
        "experimental_methods": summary[0].get("experimental_method", []),
        "assembly_id": assembly_id,
        "assemblies": assemblies,
        "initial_chain_id": chain_id,
        "model_index": 0,
        "chains": chains,
        "ligands": ligands if include_ligands else [],
        "annotations": annotations,
        "data_status": {
            "annotations": "not_requested"
            if not include_annotations
            else "unavailable"
            if any(
                "data is unavailable" in w and any(track in w for track in tracks)
                for w in warnings
            )
            else "loaded",
            "ligands": "not_requested"
            if not include_ligands
            else "unavailable"
            if any("ligand_monomers data is unavailable" in w for w in warnings)
            else "loaded",
        },
        "entry_url": f"https://www.ebi.ac.uk/pdbe/entry/pdb/{pdb_id}",
        "coordinate_url": f"https://www.ebi.ac.uk/pdbe/entry-files/download/{pdb_id}.bcif",
        "sources": sorted(sources),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
    }


def mvs_validation_failure(error: ValueError) -> types.CallToolResult:
    if isinstance(error, ValidationError):
        issues = []
        for issue in error.errors(
            include_url=False, include_input=False, include_context=False
        )[:8]:
            path = list(map(str, issue["loc"]))
            detail = {"field": ".".join(path), "message": issue["msg"][:300]}
            component_opacity = len(path) >= 3 and path[-3] in (
                "components",
                "annotations",
            )
            representation_opacity = (
                len(path) >= 4
                and path[-4] in ("components", "annotations")
                and path[-2] == "representation"
            )
            if (
                path
                and path[-1] == "opacity"
                and (component_opacity or representation_opacity)
            ):
                if len(path) < 2 or path[-2] != "representation":
                    path.insert(len(path) - 1, "representation")
                detail["suggested_field"] = ".".join(path)
                detail["hint"] = (
                    "Set opacity only in representation.opacity to a number from 0 (transparent) to 1 (opaque); remove any conflicting component-level opacity."
                )
            issues.append(detail)
    else:
        issues = [{"field": "builder", "message": str(error)[:1000]}]
    details = "\n".join(
        f"{issue['field']}: {issue['message']}"
        + (f" Correction: {issue['hint']}" if "hint" in issue else "")
        for issue in issues
    )
    return types.CallToolResult(
        isError=True,
        content=[
            types.TextContent(
                type="text",
                text="MVS validation failed. No view was created. Correct these fields and retry once with a changed specification; do not repeat the same input.\n"
                + details,
            )
        ],
        structuredContent={
            "status": "validation_failed",
            "retryable": True,
            "issues": issues,
        },
    )


def normalize_mvs_arguments(arguments, *, story=False):
    try:
        model = (BuildStoryInput if story else BuildMvsInput).model_validate(arguments)
        return model.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude_unset=True
        )
    except ValueError as error:
        return mvs_validation_failure(error)


def build_pdbe_apps_server(generator: OpenAPIToMCPGenerator | None = None) -> Server:
    server = PDBeServer("pdbe-apps-server")
    server.tool_input_normalizers = {
        "ebi-pdbe-build_mvs": normalize_mvs_arguments,
        "ebi-pdbe-build_mvs_story": lambda arguments: normalize_mvs_arguments(
            arguments, story=True
        ),
    }
    catalog = SkillCatalog()
    server.skill_catalog = catalog

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        display = request_display_options(server)
        return [
            types.Tool(
                name="pdbe_update_workspace",
                description=(
                    "Compose or restore a molecular workspace in the shared viewer. Supply the latest complete "
                    "workspace from tool results or App context, expected_revision, and atomic operations. "
                    "Supports adding/removing scenes and structures, component or annotation layers, "
                    "and changing layer visibility. IDs must match exactly. No operations validates and restores "
                    "a saved workspace. No global server state is stored. The host must route matching workspace "
                    "IDs to an existing App for cross-call updates; otherwise a new viewer opens. "
                    "The App displays supplied coordinates, transforms, residue mappings and annotations; it does not calculate scientific measurements."
                ),
                inputSchema=UpdateWorkspaceInput.model_json_schema(),
                annotations=types.ToolAnnotations(
                    readOnlyHint=True, destructiveHint=False, openWorldHint=True
                ),
                _meta={
                    "ui": {"resourceUri": display.resource_uri(WORKSPACE_RESOURCE_URI)}
                },
            ),
            types.Tool(
                name="pdbe_build_mvs_story",
                description=(
                    "Build a guided molecular story with 2–20 ordered scenes and open it in Mol* 5.13.1. "
                    "Each scene has a unique id, title, description and complete builder specification "
                    "using the same schema as build_mvs. Set component opacity inside representation.opacity, never directly on a component. Ground all narrative claims and selections "
                    "in PDBe evidence. Returns one native multi-state MVSJ with timed playback, "
                    "scene navigation and download. The host can update the originating viewer or open a new result. "
                    "Default duration is 6500 ms per scene and camera transition is 1500 ms. "
                    "Stop after a compiled result. On validation failure, correct the input and retry once; never repeat identical input. Compilation does not establish coordinate availability or verify biological claims."
                ),
                inputSchema=BuildStoryInput.model_json_schema(),
                annotations=types.ToolAnnotations(
                    readOnlyHint=True, destructiveHint=False, openWorldHint=False
                ),
                _meta={
                    "ui": {"resourceUri": display.resource_uri(WORKSPACE_RESOURCE_URI)}
                },
            ),
            types.Tool(
                name="pdbe_build_mvs",
                description=(
                    "Build a custom single-scene molecular visualization with MolViewSpec "
                    "and open it in Mol* 5.13.1. Supply a complete builder specification, "
                    "including existing choices for follow-up changes; the host routes each result to an existing viewer or a new one. "
                    "Supports chains, residue ranges, ligand instances, representations, colors, "
                    "opacity, inline annotations, labels, tooltips, focus and camera. Set component opacity inside representation.opacity, never directly on a component. "
                    "Ground selections in PDBe data; use label_seq_id for polymer residues "
                    "and auth_seq_id with insertion code for non-polymers. "
                    "Water is excluded from broad all selections unless include_water=true. "
                    "Supports density isosurfaces and clipping; structure transforms/instances, multiple structures per scene, annotation tables, primitives and serialized MolQL selectors. No raw MVS trees, executable code or PyMOL text. "
                    "Returns the complete normalized builder in structuredContent for follow-ups; "
                    "full MVSJ is delivered to the App with download support. "
                    "A compiled result completes the build; do not rebuild while waiting for viewer loading. Compilation does not verify biological claims or coordinate availability."
                ),
                inputSchema=BuildMvsInput.model_json_schema(),
                annotations=types.ToolAnnotations(
                    readOnlyHint=True, destructiveHint=False, openWorldHint=False
                ),
                _meta={
                    "ui": {"resourceUri": display.resource_uri(WORKSPACE_RESOURCE_URI)}
                },
            ),
            types.Tool(
                name="pdbe_compare_structures",
                description=(
                    "Compare two protein label chains using PDBe's precomputed "
                    "superposition matrices and SIFTS residue correspondence. "
                    "Requires a shared UniProt accession and PDBe segment containing "
                    "both chains. Opens aligned proteins first; ligands and residue annotations are opt-in "
                    "through include_ligands/include_annotations or the workspace controls. Includes PDBe/SIFTS correspondence and CSV export. "
                    "The viewer applies PDBe's transforms; no additional fitting, RMSD, "
                    "per-residue displacement or inferred binding sites are calculated."
                ),
                inputSchema=comparison_input_schema(),
                annotations=types.ToolAnnotations(
                    readOnlyHint=True, destructiveHint=False, openWorldHint=True
                ),
                _meta={
                    "ui": {"resourceUri": display.resource_uri(WORKSPACE_RESOURCE_URI)}
                },
            ),
            types.Tool(
                name="pdbe_open_structure",
                description=(
                    "Open an experimental PDB structure in an interactive 3D viewer. "
                    "Inspect chains, ligand instances and residues. Displays the first "
                    "coordinate model; defaults to the deposited asymmetric unit. A successful result completes the viewing request; stop calling this tool and let the App load coordinates."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pdb_id": {
                            "type": "string",
                            "pattern": "^[1-9][A-Za-z0-9]{3}$",
                            "description": "Four-character PDB accession, e.g. 4hhb",
                        },
                        "include_annotations": {
                            "type": "boolean",
                            "default": True,
                            "description": "Fetch supplied residue annotation records; disable for a lightweight view.",
                        },
                        "include_ligands": {
                            "type": "boolean",
                            "default": True,
                            "description": "Fetch deposited ligand instances.",
                        },
                        "assembly_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Biological assembly ID; omit for asymmetric unit",
                        },
                        "chain_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Label chain ID (struct_asym_id) to focus initially",
                        },
                    },
                    "required": ["pdb_id"],
                    "additionalProperties": False,
                },
                annotations=types.ToolAnnotations(
                    readOnlyHint=True, destructiveHint=False, openWorldHint=True
                ),
                _meta={
                    "ui": {"resourceUri": display.resource_uri(WORKSPACE_RESOURCE_URI)}
                },
            ),
        ]

    @server.call_tool()
    @tool_deadline
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        if name == "pdbe_update_workspace":
            try:
                data = await run_blocking_tool(
                    lambda: compile_workspace(update_workspace(arguments))
                )
            except ValueError as error:
                return types.CallToolResult(
                    isError=True,
                    content=[types.TextContent(type="text", text=str(error))],
                )
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text="Molecular workspace compiled. Coordinate loading is pending in the App; only supplied scientific data is displayed.",
                    )
                ],
                structuredContent={
                    "workspace": data["workspace"],
                    "status": "compiled",
                    "render_status": "pending",
                },
                _meta={"workspace": data["workspace"], "mvs": data},
            )
        if name in {"pdbe_build_mvs", "pdbe_build_mvs_story"}:
            is_story = name == "pdbe_build_mvs_story"
            try:
                data = await run_blocking_tool(
                    lambda: build_mvs_story(arguments)
                    if is_story
                    else build_mvs(arguments)
                )
            except ValueError as error:
                return mvs_validation_failure(error)
            workspace = workspace_from_mvs(data)
            data = await run_blocking_tool(lambda: compile_workspace(workspace))
            compact = {
                key: value
                for key, value in data.items()
                if key not in {"mvsj", "scenes"}
            }
            compact.update(status="compiled", render_status="pending")
            title = data["story"]["title"] if is_story else data["builder"]["title"]
            spec = {
                "version": 1,
                "story" if is_story else "builder": data[
                    "story" if is_story else "builder"
                ],
            }
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=(
                            f"Compiled {title} successfully. The build is complete; stop building and summarize the result. "
                            "The compiled MVSJ is attached to the viewer artifact; the normalized specification below is not a placeholder. "
                            "The App loads coordinates separately. Pending viewer loading is not a build error and must not trigger another build.\n"
                            # The chatbot's App wrapper currently forwards text only to the agent.
                            f"Replacement specification: {json.dumps(spec)}\n"
                            + "\n".join(data["warnings"])
                        ),
                    )
                ],
                structuredContent=compact,
                _meta={"mvs": data, "workspace": data["workspace"]},
            )
        if name == "pdbe_compare_structures":
            if not COMPARISON_UI_FILE.is_file():
                return types.CallToolResult(
                    isError=True,
                    content=[
                        types.TextContent(
                            type="text",
                            text="Build the comparison UI with npm run build in apps/structure-explorer.",
                        )
                    ],
                )
            try:
                executor = generator or await run_blocking_tool(
                    get_shared_api_generator
                )
                structures = await asyncio.gather(
                    *[
                        get_structure_data(
                            {"pdb_id": arguments[f"{side}_pdb_id"]},
                            executor,
                            include_annotations=arguments.get(
                                "include_annotations", False
                            ),
                            include_ligands=arguments.get("include_ligands", False),
                        )
                        for side in ("reference", "mobile")
                    ]
                )
                data = await run_blocking_tool(
                    lambda: comparison_data(arguments, list(structures), executor)
                )
            except (ValueError, requests.RequestException) as error:
                return types.CallToolResult(
                    isError=True,
                    content=[
                        types.TextContent(
                            type="text", text=f"PDBe comparison unavailable: {error}"
                        )
                    ],
                )
            workspace = workspace_from_comparison(data, list(structures))
            rendered = await run_blocking_tool(lambda: compile_workspace(workspace))
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=comparison_text(data))],
                structuredContent={
                    **{k: v for k, v in data.items() if k != "pairs"},
                    "workspace": rendered["workspace"],
                    "render_status": "pending",
                },
                _meta={
                    "comparison": data,
                    "workspace": rendered["workspace"],
                    "mvs": rendered,
                },
            )
        if name != "pdbe_open_structure":
            raise ValueError(f"Unknown tool name: {name}")
        if not UI_FILE.is_file():
            return types.CallToolResult(
                isError=True,
                content=[
                    types.TextContent(
                        type="text",
                        text=(
                            "Structure Explorer UI is not built. Run npm ci and npm run build "
                            "in apps/structure-explorer before starting the server."
                        ),
                    )
                ],
            )
        try:
            data = await get_structure_data(
                arguments,
                generator,
                include_annotations=arguments.get("include_annotations", True),
                include_ligands=arguments.get("include_ligands", True),
            )
        except ValueError as error:
            return types.CallToolResult(
                isError=True,
                content=[types.TextContent(type="text", text=str(error))],
            )
        compact = {
            **{key: value for key, value in data.items() if key != "annotations"},
            "annotation_summary": {
                "features": len(data["annotations"]),
                "sources": sorted({a["source"] for a in data["annotations"]}),
            },
            "chains": [
                {k: v for k, v in c.items() if k != "residues"} for c in data["chains"]
            ],
        }
        compact.update(status="prepared", render_status="pending")
        ligand_text = (
            ", ".join(
                f"{ligand['comp_id']} (author chain {ligand['auth_asym_id']}, "
                f"label chain {ligand['label_asym_id']}, residue "
                f"{ligand['auth_seq_id']}{ligand['insertion_code']})"
                for ligand in data["ligands"]
            )
            or "none reported"
        )
        text = (
            "Structure Explorer prepared successfully. The attached App contains the interactive viewer; this is not a placeholder. "
            "The tool request is complete. Do not call open_structure again to wait for browser loading.\n"
            f"{data['pdb_id'].upper()}: {data['title']}\n"
            f"Method: {', '.join(data['experimental_methods'])}\n"
            f"View: assembly {data['assembly_id'] or 'asymmetric unit'}; first coordinate model.\n"
            f"Chains (label IDs): {', '.join(c['label_asym_id'] for c in data['chains'])}\n"
            f"Ligands: {ligand_text}\nAnnotation features: {len(data['annotations'])}\nSource: {data['entry_url']}"
        )
        if data["warnings"]:
            text += "\n" + "\n".join(data["warnings"])
        workspace = workspace_from_structure(data)
        rendered = await run_blocking_tool(lambda: compile_workspace(workspace))
        compact["workspace"] = rendered["workspace"]
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structuredContent=compact,
            # Full residue lists go to the app without consuming model context.
            _meta={
                "structure": data,
                "workspace": rendered["workspace"],
                "mvs": rendered,
            },
        )

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        display = request_display_options(server)
        return [
            types.Resource(
                uri=AnyUrl(display.resource_uri(uri)),
                name=title,
                mimeType=APP_MIME_TYPE,
            )
            for uri, title in APP_RESOURCES.items()
        ] + catalog.resources()

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        if str(uri) in catalog.files:
            resource = catalog.read(str(uri))
            return [
                ReadResourceContents(
                    content=resource["text"], mime_type=resource["mimeType"]
                )
            ]
        base_uri = app_resource_base_uri(str(uri))
        if base_uri is None:
            raise ValueError(f"Unknown resource: {uri}")
        query = parse_qs(urlsplit(str(uri)).query, keep_blank_values=True)
        if any(
            key not in {"show_header", "show_search"} or len(values) != 1
            for key, values in query.items()
        ):
            raise ValueError("Invalid app resource display options")
        # The URI alone determines the HTML, even if the connection changes.
        display = AppDisplayOptions.from_query(
            {key: values[0] for key, values in query.items()}
        )
        ui_file = {
            COMPARISON_RESOURCE_URI: COMPARISON_UI_FILE,
            MVS_RESOURCE_URI: MVS_UI_FILE,
        }.get(base_uri, UI_FILE)
        if not ui_file.is_file():
            raise ValueError(
                "Build the UI with npm run build in apps/structure-explorer"
            )
        html = ui_file.read_text(encoding="utf-8").replace(
            "<html",
            '<html data-pdbe-show-header="'
            + str(display.show_header).lower()
            + '" data-pdbe-show-search="'
            + str(display.show_search).lower()
            + '"',
            1,
        )
        return [
            ReadResourceContents(
                content=html,
                mime_type=APP_MIME_TYPE,
                meta={
                    "ui": {
                        "prefersBorder": True,
                        "csp": {
                            "connectDomains": (
                                [
                                    "https://www.ebi.ac.uk",
                                    "https://ebi.ac.uk",
                                    "https://*.ebi.ac.uk",
                                    "https://wwpdb.org",
                                    "https://*.wwpdb.org",
                                ]
                            ),
                            "resourceDomains": ["data:", "blob:"],
                        },
                    }
                },
            )
        ]

    add_skill_result_metadata(server)
    return server
