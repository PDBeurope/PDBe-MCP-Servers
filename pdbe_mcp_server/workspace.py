"""Versioned, stateless molecular workspaces compiled through the existing MVS builder."""

from copy import deepcopy
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import Field, field_serializer, model_validator

from pdbe_mcp_server.mvs import (
    Annotation,
    AnnotationData,
    Camera,
    Canvas,
    Component,
    Focus,
    Primitive,
    Spec,
    Structure,
    Transition,
    Volume,
    build_mvs,
    build_mvs_story,
)

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class LigandInstance(Spec):
    label_asym_id: str = Field(min_length=1)
    auth_asym_id: str = ""
    auth_seq_id: int
    insertion_code: str = ""
    comp_id: str = Field(min_length=1)


class WorkspaceStructure(Spec):
    id: Identifier
    pdb_id: str = Field(pattern=r"^(?:[1-9][a-z0-9]{3}|pdb_[a-z0-9]{8})$")
    options: Structure = Field(default_factory=Structure)
    focus: bool | Focus = False
    include_water: bool = False
    labels_from: list[AnnotationData] = Field(default_factory=list, max_length=20)
    tooltips_from: list[AnnotationData] = Field(default_factory=list, max_length=20)
    primitives: list[Primitive] = Field(default_factory=list, max_length=100)
    sources: list[str] = Field(default_factory=list, max_length=50)
    data_sources: list[str] = Field(default_factory=list, max_length=1000)
    ligands: list[LigandInstance] = Field(default_factory=list, max_length=500)
    chains: list[dict[str, Any]] = Field(default_factory=list, max_length=10000)
    annotations: list[dict[str, Any]] = Field(default_factory=list, max_length=10000)
    data_status: dict[str, Literal["not_requested", "loaded", "unavailable"]] = Field(
        default_factory=dict
    )

    @field_serializer("options")
    def sparse_options(self, value):
        return value.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude_unset=True
        )


class WorkspaceLayer(Spec):
    id: Identifier
    structure_id: Identifier
    name: str = Field(min_length=1, max_length=2000)
    kind: Literal["component", "annotation"] = "component"
    visible: bool = True
    category: Literal["ligand", "source_annotation"] | None = None
    source_annotation_id: str | None = None
    source_annotation_ids: list[str] = Field(default_factory=list, max_length=10000)
    component: Component | None = None
    annotation: Annotation | None = None
    sources: list[str] = Field(default_factory=list, max_length=50)

    @field_serializer("component")
    def sparse_component(self, value):
        return (
            value.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            )
            if value
            else None
        )

    @model_validator(mode="after")
    def definition(self):
        expected = {
            "component": self.component,
            "annotation": self.annotation,
        }[self.kind]
        if expected is None:
            raise ValueError(f"{self.kind} layer requires its definition")
        if sum(x is not None for x in (self.component, self.annotation)) != 1:
            raise ValueError("A layer must have exactly one definition")
        return self


class WorkspaceScene(Spec):
    id: Identifier = "scene-1"
    title: str = Field(min_length=1, max_length=2000)
    description: str | None = None
    description_format: Literal["plaintext", "markdown"] = "plaintext"
    caption_format: Literal["plaintext", "markdown"] = "plaintext"
    structures: list[WorkspaceStructure] = Field(min_length=1, max_length=10)
    layers: list[WorkspaceLayer] = Field(default_factory=list, max_length=6000)
    canvas: Canvas = Field(default_factory=Canvas)
    camera: Camera | None = None
    volumes: list[Volume] = Field(default_factory=list, max_length=20)
    focus: bool | Focus = False
    duration_ms: int = Field(default=6500, ge=0, le=300000)
    transition_duration_ms: int = Field(default=1500, ge=0, le=30000)
    transition: Transition | None = None
    # Tool-produced correspondence and provenance; never executable expressions.
    comparison: dict[str, Any] | None = None

    @model_validator(mode="after")
    def references(self):
        ids = [s.id for s in self.structures]
        layer_ids = [layer.id for layer in self.layers]
        if len(ids) != len(set(ids)) or len(layer_ids) != len(set(layer_ids)):
            raise ValueError(
                "Structure and layer IDs must each be unique within a scene"
            )
        if set(ids) & set(layer_ids):
            raise ValueError("Layer IDs must differ from structure IDs")
        if any(layer.structure_id not in ids for layer in self.layers):
            raise ValueError("Layer refers to an unknown structure ID")
        if self.comparison and any(
            self.comparison.get(key) not in ids for key in ("reference_id", "mobile_id")
        ):
            raise ValueError("Comparison refers to an unknown structure ID")
        return self


class WorkspaceView(Spec):
    active_scene_id: Identifier | None = None
    cameras: dict[str, Camera] = Field(default_factory=dict)


class Workspace(Spec):
    version: Literal[1] = 1
    id: Identifier = Field(default_factory=lambda: "workspace-" + uuid4().hex)
    revision: int = Field(default=0, ge=0, strict=True)
    view: WorkspaceView = Field(default_factory=WorkspaceView)
    description: str | None = None
    description_format: Literal["plaintext", "markdown"] = "plaintext"
    title: str = Field(min_length=1, max_length=2000)
    scenes: list[WorkspaceScene] = Field(min_length=1, max_length=20)
    sources: list[str] = Field(default_factory=list, max_length=1000)
    warnings: list[str] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def unique_scenes(self):
        if len({scene.id for scene in self.scenes}) != len(self.scenes):
            raise ValueError("Scene IDs must be unique")
        ids = {scene.id for scene in self.scenes}
        if self.view.active_scene_id and self.view.active_scene_id not in ids:
            raise ValueError("Active scene does not exist")
        if self.view.cameras.keys() - ids:
            raise ValueError("Saved camera refers to an unknown scene")
        return self


class WorkspaceOperation(Spec):
    op: Literal[
        "upsert_structure",
        "remove_structure",
        "upsert_layer",
        "remove_layer",
        "set_visibility",
        "upsert_scene",
        "remove_scene",
    ]
    scene_id: Identifier
    target_id: Identifier
    scene: WorkspaceScene | None = None
    structure: WorkspaceStructure | None = None
    layer: WorkspaceLayer | None = None
    visible: bool | None = None


class UpdateWorkspaceInput(Spec):
    workspace: Workspace
    expected_revision: int = Field(ge=0, strict=True)
    operations: list[WorkspaceOperation] = Field(default_factory=list, max_length=100)
    compact_response: bool = Field(
        default=False,
        description="Return only compiled scene data and workspace revision metadata when the caller already holds the updated workspace.",
    )


def update_workspace(arguments: dict[str, Any]) -> Workspace:
    """Apply an atomic update to supplied state; no shared global workspace store."""
    request = UpdateWorkspaceInput.model_validate(arguments)
    if request.expected_revision != request.workspace.revision:
        raise ValueError("Workspace revision conflict; use the latest workspace state")
    value = request.workspace.model_dump(mode="json", exclude_none=True)
    for op in request.operations:
        scene = next((s for s in value["scenes"] if s["id"] == op.scene_id), None)
        if op.op == "upsert_scene":
            if (
                op.scene is None
                or op.scene.id != op.target_id
                or op.scene_id != op.target_id
            ):
                raise ValueError("Scene upsert ID must match scene_id and target_id")
            replacement = op.scene.model_dump(mode="json", exclude_none=True)
            if scene is None:
                value["scenes"].append(replacement)
            else:
                value["scenes"][value["scenes"].index(scene)] = replacement
            continue
        if op.op == "remove_scene":
            if scene is None or op.scene_id != op.target_id:
                raise ValueError(
                    "Scene removal requires a matching existing scene_id and target_id"
                )
            value["scenes"].remove(scene)
            value["view"]["cameras"].pop(op.scene_id, None)
            if value["view"].get("active_scene_id") == op.scene_id:
                value["view"]["active_scene_id"] = (
                    value["scenes"][0]["id"] if value["scenes"] else None
                )
            continue
        if scene is None:
            raise ValueError(f"Unknown scene ID: {op.scene_id}")
        field = "structures" if op.op.endswith("structure") else "layers"
        current = next((x for x in scene[field] if x["id"] == op.target_id), None)
        if op.op.startswith("upsert"):
            item = op.structure if field == "structures" else op.layer
            if item is None or item.id != op.target_id:
                raise ValueError("Upsert definition ID must match target_id")
            replacement = item.model_dump(mode="json", exclude_none=True)
            if current is None:
                scene[field].append(replacement)
            else:
                scene[field][scene[field].index(current)] = replacement
                if (
                    field == "structures"
                    and scene.get("comparison")
                    and op.target_id
                    in (
                        scene["comparison"].get("reference_id"),
                        scene["comparison"].get("mobile_id"),
                    )
                ):
                    # A replacement may change coordinates or the alignment frame.
                    scene.pop("comparison")
        elif current is None:
            raise ValueError(f"Unknown target ID: {op.target_id}")
        elif op.op == "set_visibility":
            if op.visible is None:
                raise ValueError("set_visibility requires visible")
            current["visible"] = op.visible
        else:
            scene[field].remove(current)
            if field == "structures":
                scene["layers"] = [
                    x for x in scene["layers"] if x["structure_id"] != op.target_id
                ]
                if scene.get("comparison") and op.target_id in (
                    scene["comparison"].get("reference_id"),
                    scene["comparison"].get("mobile_id"),
                ):
                    scene.pop("comparison")
    if request.operations:
        value["revision"] += 1
    return Workspace.model_validate(value)


def scene_builder(scene: WorkspaceScene) -> dict[str, Any]:
    structures = []
    for structure in scene.structures:
        definition = structure.model_dump(mode="json", exclude_none=True)
        options = structure.options.model_dump(
            mode="json", exclude_none=True, exclude_unset=True
        )
        options["ref"] = structure.id
        components = [
            layer.component.model_dump(
                mode="json", exclude_none=True, exclude_unset=True
            )
            for layer in scene.layers
            if layer.structure_id == structure.id
            and layer.visible
            and layer.kind == "component"
            and layer.component is not None
        ]
        annotations = [
            layer.annotation.model_dump(mode="json", exclude_none=True)
            for layer in scene.layers
            if layer.structure_id == structure.id
            and layer.visible
            and layer.kind == "annotation"
            and layer.annotation is not None
        ]
        structures.append(
            {
                **{
                    k: definition[k]
                    for k in (
                        "pdb_id",
                        "focus",
                        "include_water",
                        "labels_from",
                        "tooltips_from",
                        "primitives",
                        "sources",
                    )
                },
                "structure": options,
                # Keep coordinates available to viewing even with all layers hidden.
                "components": components
                or [
                    {
                        "selector": {"label_asym_id": "__workspace_empty__"},
                        "label": {"text": "Coordinates only (static layers hidden)"},
                    }
                ],
                "annotations": annotations,
            }
        )
    return {
        **structures[0],
        "additional_structures": structures[1:],
        **scene.model_dump(
            mode="json",
            exclude_none=True,
            include={
                "title",
                "description",
                "description_format",
                "canvas",
                "camera",
                "volumes",
                "focus",
            },
        ),
    }


def compile_workspace(workspace: Workspace) -> dict[str, Any]:
    """Use the existing, validated compiler for every workflow and capability."""

    def builder(scene):
        value = scene_builder(scene)
        if scene.id in workspace.view.cameras:
            value["camera"] = workspace.view.cameras[scene.id].model_dump(mode="json")
        return value

    if len(workspace.scenes) == 1:
        result = build_mvs({"builder": builder(workspace.scenes[0])})
    else:
        result = build_mvs_story(
            {
                "story": {
                    "title": workspace.title,
                    "description": workspace.description,
                    "description_format": workspace.description_format,
                    "scenes": [
                        {
                            "id": s.id,
                            "title": s.title,
                            "description": s.description,
                            "description_format": s.caption_format,
                            "duration_ms": s.duration_ms,
                            "transition_duration_ms": s.transition_duration_ms,
                            "builder": builder(s),
                            **(
                                {"transition": s.transition.model_dump()}
                                if s.transition
                                else {}
                            ),
                        }
                        for s in workspace.scenes
                    ],
                }
            }
        )

    def remove_placeholder(node):
        if "children" in node:
            node["children"] = [
                child
                for child in node["children"]
                if not (
                    child["kind"] == "component"
                    and child.get("params", {}).get("selector")
                    == {"label_asym_id": "__workspace_empty__"}
                )
            ]
            for child in node["children"]:
                remove_placeholder(child)

    roots = [snapshot["root"] for snapshot in result["mvsj"].get("snapshots", [])] or [
        result["mvsj"]["root"]
    ]
    for root in roots:
        remove_placeholder(root)
    result["sources"] = list(
        dict.fromkeys(
            [
                *result.get("sources", []),
                *workspace.sources,
                *(
                    url
                    for scene in workspace.scenes
                    for structure in scene.structures
                    for url in structure.data_sources
                ),
                *(
                    url
                    for scene in workspace.scenes
                    for layer in scene.layers
                    for url in layer.sources
                ),
            ]
        )
    )
    result["workspace"] = workspace.model_dump(mode="json", exclude_none=True)
    result["warnings"] = list(dict.fromkeys([*result["warnings"], *workspace.warnings]))
    return result


def workspace_from_mvs(data: dict[str, Any]) -> Workspace:
    scenes = []
    definitions = data.get("scenes") or [
        {"id": "scene-1", "title": data["builder"]["title"], "builder": data["builder"]}
    ]
    # Story results contain summary builders; use the complete normalized story specification.
    if data.get("story"):
        definitions = data["story"]["scenes"]
    for original in definitions:
        builder = deepcopy(original["builder"])
        structures, layers = [], []
        reserved = {
            source.get("structure", {}).get("ref")
            for source in [builder, *builder.get("additional_structures", [])]
        }
        assigned = set()
        for index, source in enumerate(
            [builder, *builder.get("additional_structures", [])]
        ):
            options = source.get("structure", {})
            sid = options.get("ref") or f"structure-{index + 1}"
            if not options.get("ref"):
                suffix = 1
                while sid in reserved or sid in assigned:
                    sid = f"structure-{index + 1}-auto-{suffix}"
                    suffix += 1
            assigned.add(sid)
            structures.append(
                {
                    "id": sid,
                    "pdb_id": source["pdb_id"],
                    "options": options,
                    **{
                        k: source[k]
                        for k in (
                            "focus",
                            "include_water",
                            "labels_from",
                            "tooltips_from",
                            "primitives",
                            "sources",
                        )
                        if k in source
                    },
                }
            )
            for kind, field in (
                ("component", "components"),
                ("annotation", "annotations"),
            ):
                for j, component in enumerate(source.get(field, [])):
                    layer_id = f"layer-{index + 1}-{kind}-{j + 1}"
                    suffix = 1
                    while layer_id in reserved or layer_id in assigned:
                        layer_id = f"layer-{index + 1}-{kind}-{j + 1}-auto-{suffix}"
                        suffix += 1
                    assigned.add(layer_id)
                    layers.append(
                        {
                            "id": layer_id,
                            "structure_id": sid,
                            "kind": kind,
                            "name": f"{source['pdb_id'].upper()} {kind} {j + 1}",
                            kind: component,
                        }
                    )
        scenes.append(
            {
                "id": original["id"],
                "title": original.get("title")
                or builder.get("title")
                or "Molecular scene",
                "structures": structures,
                "layers": layers,
                "caption_format": original.get("description_format", "plaintext"),
                **{
                    k: builder[k]
                    for k in (
                        "description",
                        "description_format",
                        "canvas",
                        "camera",
                        "volumes",
                        "focus",
                    )
                    if k in builder
                },
                **{
                    k: original[k]
                    for k in ("duration_ms", "transition_duration_ms", "transition")
                    if k in original
                },
            }
        )
    return Workspace.model_validate(
        {
            "title": data.get("story", {}).get("title") or data["builder"]["title"],
            "scenes": scenes,
            **{
                k: data["story"][k]
                for k in ("description", "description_format")
                if k in data.get("story", {})
            },
            "warnings": data.get("warnings", []),
            "sources": data.get("sources", []),
        }
    )


def workspace_from_structure(data: dict[str, Any]) -> Workspace:
    sid = "structure-1"
    layers = [
        {
            "id": f"chain-{i + 1}",
            "structure_id": sid,
            "name": f"Chain {c['label_asym_id']} · {c.get('name', '')}",
            "component": {
                "selector": {"label_asym_id": c["label_asym_id"]},
                "color": {"color": "#2787b5"},
                "focus": c["label_asym_id"] == data.get("initial_chain_id"),
            },
        }
        for i, c in enumerate(data["chains"])
    ]
    ligands = [
        {k: ligand[k] for k in LigandInstance.model_fields if k in ligand}
        for ligand in data.get("ligands", [])
    ]
    for i, ligand in enumerate(ligands):
        layers.append(
            {
                "id": f"ligand-{i + 1}",
                "category": "ligand",
                "structure_id": sid,
                "name": f"{ligand['comp_id']} · {ligand['label_asym_id']} {ligand['auth_seq_id']}{ligand.get('insertion_code', '')}",
                "component": {
                    "selector": {
                        "label_asym_id": ligand["label_asym_id"],
                        "auth_seq_id": ligand["auth_seq_id"],
                        "pdbx_PDB_ins_code": ligand.get("insertion_code", ""),
                        "label_comp_id": ligand["comp_id"],
                    },
                    "representation": {"type": "ball_and_stick"},
                    "color": {"color": "#e5a536"},
                },
            }
        )
    annotations = [
        {**record, "id": record.get("id", f"feature-{i}")}
        for i, record in enumerate(data.get("annotations", []))
    ]
    # One visual union per provider/source/chain. Keep the original sites and raw
    # per-residue values in metadata; a dense track must not create 1000 components.
    groups = {}
    for annotation in annotations:
        for segment in annotation["segments"]:
            key = (
                annotation["source"],
                annotation.get("source_url", ""),
                segment["label_asym_id"],
                annotation.get("kind") or "features",
            )
            group = groups.setdefault(key, {"ids": [], "ranges": []})
            if annotation["id"] not in group["ids"]:
                group["ids"].append(annotation["id"])
            group["ranges"].append((segment["start"], segment["end"]))
    for i, ((provider, source_url, chain_id, annotation_kind), group) in enumerate(
        groups.items()
    ):
        ranges = []
        for start, end in sorted(set(group["ranges"])):
            if ranges and start <= ranges[-1][1] + 1:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
            else:
                ranges.append((start, end))
        selectors = [
            {
                "label_asym_id": chain_id,
                "beg_label_seq_id": start,
                "end_label_seq_id": end,
            }
            for start, end in ranges
        ]
        layers.append(
            {
                "id": f"annotation-{i + 1}",
                "category": "source_annotation",
                "source_annotation_ids": group["ids"],
                "structure_id": sid,
                "name": f"{provider} · {annotation_kind} · chain {chain_id}",
                "visible": False,
                "component": {
                    "selector": selectors,
                    "representation": {"type": "ball_and_stick"},
                    "color": {"color": "#9473bc"},
                    "tooltip": f"{provider} {annotation_kind}: supplied annotation coverage",
                },
                "sources": [source_url] if source_url else [],
            }
        )
    options = (
        {"type": "assembly", "assembly_id": data["assembly_id"]}
        if data.get("assembly_id")
        else {}
    )
    return Workspace.model_validate(
        {
            "title": data["title"],
            "sources": data.get("sources", []),
            "warnings": data.get("warnings", []),
            "scenes": [
                {
                    "title": data["title"],
                    "structures": [
                        {
                            "id": sid,
                            "pdb_id": data["pdb_id"],
                            "options": options,
                            "ligands": ligands,
                            "chains": data.get("chains", []),
                            "annotations": annotations,
                            "data_status": data.get("data_status", {}),
                            "data_sources": data.get("sources", []),
                        }
                    ],
                    "layers": layers,
                }
            ],
        }
    )


def workspace_from_comparison(
    data: dict[str, Any], structures: list[dict[str, Any]]
) -> Workspace:
    scene_structures, layers = [], []
    for key, structure, color in zip(
        ("reference", "mobile"), structures, ("#2787b5", "#db4a39")
    ):
        side = data[key]
        # Limit coverage and annotation selections to the actual compared label chain.
        selected = deepcopy(structure)
        chain_id = side["chain"]["label_asym_id"]
        selected["chains"] = [
            c for c in structure["chains"] if c["label_asym_id"] == chain_id
        ]
        selected["annotations"] = [
            {
                **a,
                "segments": [
                    s for s in a["segments"] if s["label_asym_id"] == chain_id
                ],
            }
            for a in structure.get("annotations", [])
            if any(s["label_asym_id"] == chain_id for s in a["segments"])
        ]
        source = workspace_from_structure(selected).scenes[0]
        definition = source.structures[0].model_dump(mode="json", exclude_none=True)
        definition.update(
            id=key,
            options={
                "transform": {
                    "matrix": [
                        side["matrix"][row][col] for col in range(4) for row in range(4)
                    ]
                }
            },
        )
        scene_structures.append(definition)
        layers.append(
            {
                "id": f"{key}-protein",
                "structure_id": key,
                "name": f"{side['pdb_id'].upper()} chain {side['chain']['label_asym_id']}",
                "component": {
                    "selector": {"label_asym_id": side["chain"]["label_asym_id"]},
                    "color": {"color": color},
                },
            }
        )
        # Reuse explicit ligand instances and source annotations, without inferring sites.
        for layer in source.layers:
            if layer.id.startswith(("ligand-", "annotation-")):
                supplied = layer.model_dump(mode="json", exclude_none=True)
                supplied.update(
                    id=f"{key}-{layer.id}",
                    structure_id=key,
                    name=f"{side['pdb_id'].upper()} · {layer.name}",
                )
                layers.append(supplied)
    return Workspace.model_validate(
        {
            "title": f"{data['reference']['pdb_id'].upper()} / {data['mobile']['pdb_id'].upper()} comparison",
            "sources": data["sources"],
            "warnings": data["warnings"],
            "scenes": [
                {
                    "title": "Aligned protein comparison",
                    "structures": scene_structures,
                    "layers": layers,
                    "comparison": {
                        **data,
                        "reference_id": "reference",
                        "mobile_id": "mobile",
                    },
                }
            ],
        }
    )
