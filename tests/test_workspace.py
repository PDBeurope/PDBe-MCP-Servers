"""Composition, atomic updates, round trips and scientific provenance."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from pdbe_mcp_server.mvs import Camera, build_mvs, build_mvs_story
from pdbe_mcp_server.workspace import (
    Workspace,
    compile_workspace,
    update_workspace,
    workspace_from_comparison,
    workspace_from_mvs,
    workspace_from_structure,
)


def workspace():
    return workspace_from_mvs(
        build_mvs(
            {
                "builder": {
                    "pdb_id": "1cbs",
                    "components": [
                        {"selector": "polymer", "color": {"color": "#2787b5"}},
                        {
                            "selector": "ligand",
                            "representation": {"type": "ball_and_stick"},
                        },
                    ],
                }
            }
        )
    )


def nodes(node):
    yield node
    for child in node.get("children", []):
        yield from nodes(child)


def test_visibility_updates_preserve_other_layers_sources_and_saved_view():
    original = workspace()
    original.sources = ["https://example.test/evidence"]
    original.view.active_scene_id = "scene-1"
    first, second = original.scenes[0].layers
    updated = update_workspace(
        {
            "workspace": original.model_dump(mode="json"),
            "expected_revision": 0,
            "operations": [
                {
                    "op": "set_visibility",
                    "scene_id": "scene-1",
                    "target_id": first.id,
                    "visible": False,
                }
            ],
        }
    )
    assert updated.id == original.id and updated.revision == 1
    assert original.scenes[0].layers[0].visible  # no mutation on supplied base
    assert not updated.scenes[0].layers[0].visible
    assert updated.scenes[0].layers[1] == second
    assert updated.sources == original.sources and updated.view == original.view
    compiled = compile_workspace(updated)
    assert [
        n["params"]["selector"]
        for n in nodes(compiled["mvsj"]["root"])
        if n["kind"] == "component"
    ] == ["ligand"]
    restored = update_workspace(
        {
            "workspace": json.loads(updated.model_dump_json()),
            "expected_revision": 1,
            "operations": [],
        }
    )
    assert restored == updated


def test_updates_are_atomic_and_reject_stale_or_dangling_references():
    original = workspace().model_dump(mode="json")
    before = deepcopy(original)
    with pytest.raises(ValueError, match="revision conflict"):
        update_workspace(
            {"workspace": original, "expected_revision": 1, "operations": []}
        )
    with pytest.raises(ValueError, match="unknown structure"):
        update_workspace(
            {
                "workspace": original,
                "expected_revision": 0,
                "operations": [
                    {
                        "op": "upsert_layer",
                        "scene_id": "scene-1",
                        "target_id": "bad",
                        "layer": {
                            "id": "bad",
                            "structure_id": "missing",
                            "name": "Bad",
                            "component": {"selector": "all"},
                        },
                    }
                ],
            }
        )
    assert original == before
    assert workspace().id != workspace().id


def test_add_structure_and_supplied_layer_then_remove_cleans_dependent_layers():
    original = workspace()
    updated = update_workspace(
        {
            "workspace": original.model_dump(mode="json"),
            "expected_revision": 0,
            "operations": [
                {
                    "op": "upsert_structure",
                    "scene_id": "scene-1",
                    "target_id": "other",
                    "structure": {"id": "other", "pdb_id": "2g2f"},
                },
                {
                    "op": "upsert_layer",
                    "scene_id": "scene-1",
                    "target_id": "site",
                    "layer": {
                        "id": "site",
                        "structure_id": "other",
                        "name": "Supplied annotated residues",
                        "kind": "component",
                        "component": {
                            "selector": {
                                "label_asym_id": "A",
                                "beg_label_seq_id": 10,
                                "end_label_seq_id": 20,
                            }
                        },
                        "sources": ["https://example.test/annotation"],
                    },
                },
            ],
        }
    )
    assert len(updated.scenes[0].structures) == 2
    assert any(
        n.get("ref") == "other"
        for n in nodes(compile_workspace(updated)["mvsj"]["root"])
    )
    removed = update_workspace(
        {
            "workspace": updated.model_dump(mode="json"),
            "expected_revision": 1,
            "operations": [
                {"op": "remove_structure", "scene_id": "scene-1", "target_id": "other"}
            ],
        }
    )
    assert len(removed.scenes[0].structures) == 1
    assert all(layer.id != "site" for layer in removed.scenes[0].layers)


def test_builder_features_survive_workspace_roundtrip():
    fixtures = json.loads(Path("tests/fixtures/mvs_extended.json").read_text())
    # Fixtures contain builder requests and expected compiled outputs.
    assert fixtures
    for fixture in fixtures:
        arguments = fixture.get("input") or fixture.get("arguments")
        if arguments is None:
            continue
        compiled = build_mvs(
            arguments if "builder" in arguments else {"builder": arguments}
        )
        restored = compile_workspace(workspace_from_mvs(compiled))

        # Stable workspace refs are added to structures that had no explicit ref.
        def strip_refs(value):
            if isinstance(value, dict):
                return {k: strip_refs(v) for k, v in value.items() if k != "ref"}
            if isinstance(value, list):
                return [strip_refs(v) for v in value]
            return value

        assert strip_refs(restored["mvsj"]["root"]) == strip_refs(
            compiled["mvsj"]["root"]
        )


def test_story_roundtrip_preserves_captions_transitions_and_structure_transforms():
    matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, 20, 30, 1]
    data = build_mvs_story(
        {
            "story": {
                "title": "Story",
                "description": "Context",
                "scenes": [
                    {
                        "id": "first",
                        "title": "First",
                        "description": "Caption",
                        "transition": {"trajectory": "leap"},
                        "builder": {
                            "pdb_id": "1cbs",
                            "structure": {
                                "ref": "protein",
                                "transform": {"matrix": matrix},
                            },
                        },
                    },
                    {"id": "second", "title": "Second", "builder": {"pdb_id": "2g2f"}},
                ],
            }
        }
    )
    restored = compile_workspace(workspace_from_mvs(data))
    assert restored["story"]["description"] == "Context"
    assert restored["story"]["scenes"][0]["description"] == "Caption"
    assert restored["story"]["scenes"][0]["transition"]["trajectory"] == "leap"
    assert (
        restored["story"]["scenes"][0]["builder"]["structure"]["transform"]["matrix"]
        == matrix
    )


def test_explorer_and_comparison_use_the_same_layer_contract():
    structure = {
        "pdb_id": "1cbs",
        "title": "Example",
        "assembly_id": None,
        "chains": [{"label_asym_id": "A", "name": "Protein"}],
        "ligands": [
            {
                "label_asym_id": "B",
                "auth_asym_id": "A",
                "auth_seq_id": 500,
                "insertion_code": "C",
                "comp_id": "LIG",
            }
        ],
        "annotations": [
            {
                "source": "PDBe",
                "name": "Pocket",
                "description": "Observed pocket",
                "source_url": "https://example.test/site",
                "segments": [{"label_asym_id": "A", "start": 1, "end": 10}],
            }
        ],
        "sources": [],
        "warnings": [],
    }
    explorer = workspace_from_structure(structure)
    assert len(explorer.scenes[0].layers) == 3
    compile_workspace(explorer)
    side = {
        "pdb_id": "1cbs",
        "chain": {"label_asym_id": "A"},
        "matrix": [[1, 0, 0, 10], [0, 1, 0, 20], [0, 0, 1, 30], [0, 0, 0, 1]],
    }
    comparison = workspace_from_comparison(
        {"reference": side, "mobile": side, "pairs": [], "sources": [], "warnings": []},
        [structure, structure],
    )
    assert comparison.scenes[0].structures[0].options.transform.matrix[12:15] == [
        10,
        20,
        30,
    ]
    ligand_layer = next(
        layer
        for layer in comparison.scenes[0].layers
        if layer.id == "reference-ligand-1"
    )
    assert ligand_layer.component.selector.pdbx_PDB_ins_code == "C"
    annotation_layer = next(
        layer
        for layer in comparison.scenes[0].layers
        if layer.id == "reference-annotation-1"
    )
    assert annotation_layer.sources == ["https://example.test/site"]
    assert annotation_layer.component.selector[0].beg_label_seq_id == 1
    assert annotation_layer.component.selector[0].end_label_seq_id == 10
    assert all(
        layer.kind in {"component", "annotation"}
        for layer in comparison.scenes[0].layers
    )
    assert comparison.scenes[0].comparison["reference_id"] == "reference"
    compile_workspace(comparison)


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"view": {"active_scene_id": "missing"}},
    ],
)
def test_restore_rejects_unsupported_versions_and_invalid_saved_view(change):
    saved = workspace().model_dump(mode="json")
    saved.update(change)
    with pytest.raises(ValueError):
        Workspace.model_validate(saved)


def test_scene_composition_and_saved_camera_roundtrip():
    original = workspace()
    scene = original.scenes[0].model_dump(mode="json", exclude_none=True)
    scene["id"] = "second"
    updated = update_workspace(
        {
            "workspace": original.model_dump(mode="json", exclude_none=True),
            "expected_revision": 0,
            "operations": [
                {
                    "op": "upsert_scene",
                    "scene_id": "second",
                    "target_id": "second",
                    "scene": scene,
                }
            ],
        }
    )
    assert len(compile_workspace(updated)["mvsj"]["snapshots"]) == 2
    saved = updated.model_dump(mode="json", exclude_none=True)
    camera = {"position": [0, 0, 100], "target": [0, 0, 0], "up": [0, 1, 0]}
    saved["view"] = {"active_scene_id": "second", "cameras": {"second": camera}}
    compiled = compile_workspace(Workspace.model_validate(saved))
    camera_node = next(
        n
        for n in compiled["mvsj"]["snapshots"][1]["root"]["children"]
        if n["kind"] == "camera"
    )
    assert camera_node["params"] == camera
    removed = update_workspace(
        {
            "workspace": saved,
            "expected_revision": 1,
            "operations": [
                {"op": "remove_scene", "scene_id": "second", "target_id": "second"}
            ],
        }
    )
    assert removed.view.active_scene_id == "scene-1" and not removed.view.cameras


def test_generated_ids_do_not_collide_with_explicit_builder_references():
    source = build_mvs(
        {
            "builder": {
                "pdb_id": "1cbs",
                "structure": {"ref": "structure-2"},
                "additional_structures": [
                    {"pdb_id": "2g2f"},
                    {"pdb_id": "1hho", "structure": {"ref": "layer-1-component-1"}},
                ],
            }
        }
    )
    w = workspace_from_mvs(source)
    ids = [s.id for s in w.scenes[0].structures] + [
        layer.id for layer in w.scenes[0].layers
    ]
    assert len(ids) == len(set(ids))
    compile_workspace(w)


@pytest.mark.parametrize("kind", ["binding_site", "proximity"])
def test_calculated_site_layers_are_rejected_on_update_and_restore(kind):
    saved = workspace().model_dump(mode="json", exclude_none=True)
    layer = {
        "id": "calculated-site",
        "structure_id": saved["scenes"][0]["structures"][0]["id"],
        "name": "Inferred site",
        "kind": kind,
        "cutoff_angstrom": 5,
        "ligand": {"label_asym_id": "B", "auth_seq_id": 500, "comp_id": "LIG"},
        "chain_id": "A",
    }
    with pytest.raises(ValueError):
        update_workspace(
            {
                "workspace": saved,
                "expected_revision": 0,
                "operations": [
                    {
                        "op": "upsert_layer",
                        "scene_id": "scene-1",
                        "target_id": layer["id"],
                        "layer": layer,
                    }
                ],
            }
        )
    saved["scenes"][0]["layers"].append(layer)
    with pytest.raises(ValueError):
        Workspace.model_validate(saved)


def test_optional_metadata_scene_update_preserves_alignment_and_camera():
    original = workspace()
    scene = original.scenes[0].model_dump(mode="json", exclude_none=True)
    original.view.cameras[scene["id"]] = Camera(
        position=[1, 2, 3], target=[0, 0, 0], up=[0, 1, 0]
    )
    scene["comparison"] = {
        "reference_id": scene["structures"][0]["id"],
        "mobile_id": scene["structures"][0]["id"],
        "pairs": [{"uniprot_position": 42}],
    }
    original.scenes[0].comparison = scene["comparison"]
    scene["structures"][0]["data_status"] = {"annotations": "loaded"}
    scene["structures"][0]["annotations"] = [
        {
            "source": "provider",
            "segments": [
                {"label_asym_id": "A", "start": 1, "end": 2, "details": {"raw": 0.4}}
            ],
        }
    ]
    updated = update_workspace(
        {
            "workspace": original.model_dump(mode="json"),
            "expected_revision": original.revision,
            "operations": [
                {
                    "op": "upsert_scene",
                    "scene_id": scene["id"],
                    "target_id": scene["id"],
                    "scene": scene,
                }
            ],
        }
    )
    assert updated.scenes[0].comparison == original.scenes[0].comparison
    assert (
        updated.scenes[0].structures[0].options
        == original.scenes[0].structures[0].options
    )
    assert updated.view == original.view
    assert updated.scenes[0].structures[0].data_status == {"annotations": "loaded"}
    assert original.scenes[0].structures[0].annotations == []


def test_dense_provider_tracks_have_one_visual_union_but_keep_all_raw_values():
    data = {
        "pdb_id": "2dn2",
        "title": "Dense track",
        "chains": [{"label_asym_id": "A", "name": "Protein"}],
        "annotations": [
            {
                "id": f"raw-{i}",
                "source": "p2rank",
                "name": "p2rank",
                "source_url": "https://example.test/p2rank",
                "segments": [
                    {
                        "label_asym_id": "A",
                        "start": i,
                        "end": i,
                        "details": {"score": i / 200},
                    }
                ],
            }
            for i in range(1, 201)
        ],
    }
    w = workspace_from_structure(data)
    scene = w.scenes[0]
    assert len(scene.layers) == 2
    annotation = scene.layers[1]
    assert len(annotation.source_annotation_ids) == 200
    assert annotation.component.selector[0].beg_label_seq_id == 1
    assert annotation.component.selector[0].end_label_seq_id == 200
    assert len(scene.structures[0].annotations) == 200
    assert scene.structures[0].annotations[0]["segments"][0]["details"] == {
        "score": 0.005
    }
    annotation.visible = True
    compile_workspace(w)  # Previously exceeded the builder's 100-component limit.


def test_optional_lookup_provenance_is_metadata_not_a_limited_builder_argument():
    sources = [f"https://example.test/evidence/{i}" for i in range(60)]
    w = workspace_from_structure(
        {
            "pdb_id": "2dn2",
            "title": "Evidence",
            "chains": [{"label_asym_id": "A", "name": "Protein"}],
            "sources": sources,
        }
    )
    assert w.scenes[0].structures[0].data_sources == sources
    w.sources = []  # A subsequent scene enrichment keeps its own retrieval evidence.
    assert set(compile_workspace(w)["sources"]) >= set(sources)
