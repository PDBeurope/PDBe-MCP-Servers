"""Scene semantics and protocol delivery, including pdbe-chat builder patterns."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from pdbe_mcp_server.mvs import BuildMvsInput, build_mvs, build_mvs_story


def nodes(value, kind):
    if isinstance(value, dict):
        if value.get("kind") == kind:
            yield value
        for child in value.values():
            yield from nodes(child, kind)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child, kind)


def compile_scene(**builder):
    return build_mvs({"builder": {"pdb_id": "1cbs", **builder}})


def test_default_scene_is_downloadable_mvs_with_roundtrippable_spec():
    result = compile_scene(pdb_id="1CBS")
    assert result["mvsj"]["kind"] == "single"
    assert next(nodes(result["mvsj"], "download"))["params"]["url"].endswith(
        "/1cbs.bcif"
    )
    assert next(nodes(result["mvsj"], "representation"))["params"]["type"] == "cartoon"
    assert next(nodes(result["mvsj"], "structure"))["params"]["model_index"] == 0
    again = build_mvs({"version": 1, "builder": result["builder"]})
    assert again["mvsj"]["root"] == result["mvsj"]["root"]
    assert again["builder"] == result["builder"]


def test_native_animation_tracks_compile_with_references_and_roundtrip():
    builder = {
        "pdb_id": "1cbs",
        "structure": {
            "ref": "structure",
            "transform": {"translation": [-10, 0, 0], "ref": "xform"},
        },
        "components": [
            {
                "selector": "ligand",
                "representation": {
                    "type": "ball_and_stick",
                    "ref": "ligand",
                    "opacity": 0,
                    "opacity_ref": "ligand-opacity",
                    "emissive": 0,
                },
                "color": {"color": "blue", "ref": "ligand-color"},
            }
        ],
        "animation": {
            "autoplay": True,
            "loop": False,
            "duration_ms": 4000,
            "trackball": {"name": "rock", "speed": 0.15},
            "interpolations": [
                {
                    "kind": "scalar",
                    "target_ref": "ligand-opacity",
                    "property": "opacity",
                    "duration_ms": 500,
                    "start_ms": 1000,
                    "end": 1,
                },
                {
                    "kind": "color",
                    "target_ref": "ligand-color",
                    "property": "color",
                    "duration_ms": 1000,
                    "end": "red",
                    "palette": {"kind": "continuous", "colors": ["blue", "red"]},
                },
                {
                    "kind": "vec3",
                    "target_ref": "xform",
                    "property": "translation",
                    "duration_ms": 2000,
                    "end": [0, 0, 0],
                },
                {
                    "kind": "rotation_matrix",
                    "target_ref": "xform",
                    "property": "rotation",
                    "duration_ms": 2000,
                    "noise_magnitude": 0.2,
                },
                {
                    "kind": "transform_matrix",
                    "target_ref": "xform",
                    "property": "matrix",
                    "duration_ms": 2000,
                    "translation_end": [0, 0, 0],
                    "rotation_frequency": 2,
                    "rotation_alternate_direction": True,
                },
                {
                    "kind": "scalar",
                    "target_ref": "ligand",
                    "property": [
                        "custom",
                        "molstar_representation_params",
                        "emissive",
                    ],
                    "duration_ms": 2000,
                    "frequency": 4,
                    "alternate_direction": True,
                    "end": 1,
                },
            ],
        },
    }
    result = build_mvs({"builder": builder})
    root = result["mvsj"]["root"]
    animation = next(nodes(root, "animation"))
    assert animation["params"]["autoplay"] is True
    assert animation["custom"]["molstar_trackball"]["name"] == "rock"
    assert len(list(nodes(animation, "interpolate"))) == 6
    assert next(nodes(root, "transform"))["ref"] == "xform"
    rep = next(nodes(root, "representation"))
    assert rep["ref"] == "ligand"
    assert rep["custom"]["molstar_representation_params"]["emissive"] == 0
    assert next(nodes(root, "opacity"))["ref"] == "ligand-opacity"
    assert next(nodes(root, "color"))["ref"] == "ligand-color"
    again = build_mvs({"builder": result["builder"]})
    assert again["mvsj"]["root"] == root


def test_story_rejects_autoplay_animation_that_outlives_scene():
    data = story_input()
    scene = data["story"]["scenes"][0]
    scene["builder"]["components"] = [
        {"representation": {"opacity": 0, "opacity_ref": "protein-opacity"}}
    ]
    scene["builder"]["animation"] = {
        "interpolations": [
            {
                "kind": "scalar",
                "target_ref": "protein-opacity",
                "property": "opacity",
                "duration_ms": 8000,
                "end": 1,
            }
        ]
    }
    with pytest.raises(ValueError, match="Scene duration_ms"):
        build_mvs_story(data)


def test_story_animation_is_compiled_inside_its_native_snapshot():
    data = story_input()
    data["story"]["scenes"][0]["builder"]["components"] = [
        {
            "selector": "polymer",
            "representation": {"opacity": 0, "opacity_ref": "protein-opacity"},
        }
    ]
    data["story"]["scenes"][0]["builder"]["animation"] = {
        "interpolations": [
            {
                "kind": "scalar",
                "target_ref": "protein-opacity",
                "property": "opacity",
                "duration_ms": 500,
                "end": 1,
            }
        ]
    }
    result = build_mvs_story(data)
    assert len(list(nodes(result["mvsj"]["snapshots"][0]["root"], "animation"))) == 1
    assert not list(nodes(result["mvsj"]["snapshots"][1]["root"], "animation"))
    again = build_mvs_story({"story": result["story"]})
    assert again["mvsj"]["snapshots"] == result["mvsj"]["snapshots"]


@pytest.mark.parametrize(
    "animation,components",
    [
        (
            {
                "interpolations": [
                    {
                        "kind": "scalar",
                        "target_ref": "missing",
                        "property": "opacity",
                        "duration_ms": 10,
                    }
                ]
            },
            [{"representation": {"opacity": 0, "opacity_ref": "real"}}],
        ),
        (
            {
                "interpolations": [
                    {
                        "kind": "scalar",
                        "target_ref": "alpha",
                        "property": "opacity",
                        "duration_ms": 10,
                        "end": 1,
                    }
                ]
            },
            [{"color": {"color": "blue", "ref": "alpha"}}],
        ),
        (
            {
                "interpolations": [
                    {
                        "kind": "scalar",
                        "target_ref": "rep",
                        "property": [
                            "custom",
                            "molstar_representation_params",
                            "emissive",
                        ],
                        "duration_ms": 10,
                        "end": 1,
                    }
                ]
            },
            [{"representation": {"ref": "rep"}}],
        ),
    ],
)
def test_animation_rejects_unknown_or_incompatible_references(animation, components):
    with pytest.raises(ValueError):
        compile_scene(components=components, animation=animation)


@pytest.mark.parametrize(
    "kind,property_value",
    [
        ("scalar", "translation"),
        ("vec3", "position"),
        ("rotation_matrix", "translation"),
        ("transform_matrix", "translation"),
    ],
)
def test_transform_animation_rejects_unsupported_properties(kind, property_value):
    animation = {
        "interpolations": [
            {
                "kind": kind,
                "target_ref": "xform",
                "property": property_value,
                "duration_ms": 10,
            }
        ]
    }
    with pytest.raises(ValueError):
        compile_scene(
            structure={"transform": {"translation": [0, 0, 0], "ref": "xform"}},
            animation=animation,
        )


def test_residue_ranges_and_ligand_instances_preserve_identifier_systems():
    polymer = {"label_asym_id": "A", "beg_label_seq_id": 10, "end_label_seq_id": 20}
    ligand = {
        "label_asym_id": "B",
        "auth_seq_id": 150,
        "pdbx_PDB_ins_code": "A",
        "instance_id": "ASM-X0-1",
    }
    result = compile_scene(
        structure={"type": "assembly", "assembly_id": "1"},
        components=[
            {"selector": polymer, "color": "blue", "label": "Domain"},
            {
                "selector": ligand,
                "representation": "sticks",
                "label": "Ligand",
                "focus": {"radius_factor": 1.5},
            },
        ],
    )
    selectors = [
        node["params"]["selector"] for node in nodes(result["mvsj"], "component")
    ]
    assert selectors == [polymer, ligand]
    assert next(nodes(result["mvsj"], "structure"))["params"]["assembly_id"] == "1"
    assert list(nodes(result["mvsj"], "focus"))[0]["params"]["radius_factor"] == 1.5
    assert len(result["legend"]) == 2


def test_annotation_groups_have_one_label_and_individual_colors_and_tooltips():
    result = compile_scene(
        annotations=[
            {
                "selector": {"label_asym_id": "A", "label_seq_id": seq},
                "group_id": "site",
                "label": "Binding site",
                "color": color,
                "tooltip": f"Evidence {seq}",
            }
            for seq, color in [(10, "red"), (20, "blue")]
        ]
    )
    labels = list(nodes(result["mvsj"], "label"))
    assert [label["params"]["text"] for label in labels] == ["Binding site"]
    union = list(nodes(result["mvsj"], "component"))[-1]
    assert union["params"]["selector"] == [
        {"label_asym_id": "A", "label_seq_id": 10},
        {"label_asym_id": "A", "label_seq_id": 20},
    ]
    assert len(list(nodes(result["mvsj"], "tooltip"))) == 2


def test_annotations_without_groups_allow_coloring_and_tooltips_without_labels():
    result = compile_scene(
        annotations=[
            {"selector": "ligand", "color": "red", "tooltip": "Ligand evidence"}
        ]
    )
    assert not list(nodes(result["mvsj"], "label"))
    assert any(
        node["params"]["text"] == "Ligand evidence"
        for node in nodes(result["mvsj"], "tooltip")
    )


def test_all_omits_water_and_explicit_water_requires_opt_in():
    result = compile_scene(components=[{"selector": "all"}])
    assert {n["params"]["selector"] for n in nodes(result["mvsj"], "component")} == {
        "polymer",
        "branched",
        "ligand",
        "ion",
    }
    with pytest.raises(ValueError, match="include_water"):
        compile_scene(components=[{"selector": "water"}])
    assert (
        next(
            nodes(
                compile_scene(include_water=True, components=[{"selector": "water"}])[
                    "mvsj"
                ],
                "component",
            )
        )["params"]["selector"]
        == "water"
    )


@pytest.mark.parametrize(
    "structure",
    [
        {"type": "model", "model_index": 2},
        {"type": "assembly", "assembly_id": "1"},
        {"type": "symmetry", "ijk_min": [0, 0, 0], "ijk_max": [1, 1, 1]},
        {"type": "symmetry_mates", "radius": 8},
    ],
)
def test_structure_modes_roundtrip(structure):
    result = compile_scene(structure=structure)
    again = compile_scene(
        **{k: v for k, v in result["builder"].items() if k != "pdb_id"}
    )
    assert result["mvsj"]["root"] == again["mvsj"]["root"]


@pytest.mark.parametrize(
    "builder",
    [
        {"components": [{"selector": {"chain": "A"}}]},
        {"components": [{"selector": {}}]},
        {"components": [{"selector": {"label_seq_id": True}}]},
        {
            "components": [
                {"selector": {"beg_label_seq_id": 20, "end_label_seq_id": 10}}
            ]
        },
        {"components": [{"selector": {"pymol": "chain A"}}]},
        {"components": [{"representation": "made_up"}]},
        {"components": [{"representation": {"opacity": 2}}]},
        {"components": [{"representation": {"color": "red"}}]},
        {"components": [{"color": "made_up"}]},
        {"components": "invalid"},
        {"camera": {"position": [0, 0, 0], "target": [0, 0, 0]}},
        {"focus": {"radius_factor": float("nan")}},
        {"structure": {"type": "assembly", "assembly_id": ""}},
        {"structure": {"type": "model", "assembly_id": "1"}},
        {"structure": {"type": "symmetry", "ijk_max": [100, 100, 100]}},
        {"structure": {"url": "https://www.ebi.ac.uk.evil.test/a.bcif"}},
        {"structure": {"url": "http://www.ebi.ac.uk/a.bcif"}},
        {"structure": {"format": "mmcif"}},
        {"volumes": [{"url": "https://evil.test/density"}]},
        {"primitives": [{"type": "arrow"}]},
    ],
)
def test_invalid_or_unsupported_fields_are_rejected(builder):
    with pytest.raises(ValueError):
        compile_scene(**builder)


def test_replacement_preserves_previous_scene_and_does_not_mutate_input():
    first = compile_scene(
        components=[
            {"selector": "polymer", "color": "red"},
            {"selector": "ligand", "representation": "sticks"},
        ]
    )
    replacement = deepcopy(first["builder"])
    replacement["components"][0]["color"] = "blue"
    original = deepcopy(replacement)
    next_scene = build_mvs({"builder": replacement})
    assert replacement == original
    assert next_scene["builder"]["components"][1] == first["builder"]["components"][1]
    assert first["builder"]["components"][0]["color"]["color"] == "red"


def test_extended_pdb_ids_are_preserved():
    assert compile_scene(pdb_id="PDB_1000AXYZ")["coordinate_url"].endswith(
        "pdb_1000axyz.bcif"
    )


def test_provider_coordinate_url_builds_without_a_pdb_id():
    url = "https://alphafold.ebi.ac.uk/files/AF-Q9I1F6-F1-model_v6.bcif"
    result = build_mvs(
        {
            "builder": {
                "title": "Predicted structure",
                "structure": {"url": url, "format": "bcif"},
                "model_id": "AF-Q9I1F6-F1",
                "source_name": "AlphaFold DB",
                "model_kind": "predicted",
                "display_name": "Q9I1F6 predicted model",
            }
        }
    )
    assert result["coordinate_url"] == url
    assert "pdb_id" not in result["builder"]
    assert result["builder"]["model_id"] == "AF-Q9I1F6-F1"
    assert result["builder"]["model_kind"] == "predicted"
    assert next(nodes(result["mvsj"], "download"))["params"]["url"] == url


def test_non_pdbe_coordinate_filename_does_not_become_a_pdb_id():
    result = build_mvs(
        {
            "builder": {
                "structure": {
                    "url": "https://alphafold.ebi.ac.uk/files/1cbs.bcif",
                    "format": "bcif",
                }
            }
        }
    )
    assert "pdb_id" not in result["builder"]


def test_story_scenes_can_load_different_provider_sources():
    data = story_input()
    url = "https://alphafold.ebi.ac.uk/files/AF-Q9I1F6-F1-model_v6.bcif"
    data["story"]["scenes"][1]["builder"] = {
        "structure": {"url": url, "format": "bcif"},
        "model_id": "AF-Q9I1F6-F1",
        "source_name": "AlphaFold DB",
        "model_kind": "predicted",
    }
    result = build_mvs_story(data)
    assert next(nodes(result["mvsj"]["snapshots"][0]["root"], "download"))["params"][
        "url"
    ].endswith("/1cbs.bcif")
    assert next(nodes(result["mvsj"]["snapshots"][1]["root"], "download"))["params"][
        "url"
    ] == url
    assert result["story"]["scenes"][1]["builder"]["model_kind"] == "predicted"


def test_schema_describes_nested_scene_and_forbids_unknown_fields():
    schema = BuildMvsInput.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Scene"]["additionalProperties"] is False
    assert "annotations" in schema["$defs"]["Scene"]["properties"]


@pytest.mark.parametrize(
    "fixture",
    json.loads((Path(__file__).parent / "fixtures/mvs_scenes.json").read_text()),
    ids=lambda f: f["name"],
)
def test_shared_molstar_fixtures_match_python_compiler(fixture):
    compiled = build_mvs(fixture["input"])["mvsj"]
    assert compiled["root"] == fixture["mvsj"]["root"]
    assert compiled["metadata"]["version"] == fixture["mvsj"]["metadata"]["version"]


def story_input():
    return {
        "version": 1,
        "story": {
            "title": "Protein and ligand",
            "scenes": [
                {"id": "overview", "title": "Overview", "builder": {"pdb_id": "1cbs"}},
                {
                    "id": "ligand",
                    "title": "Ligand",
                    "duration_ms": 0,
                    "transition_duration_ms": 0,
                    "builder": {
                        "pdb_id": "1cbs",
                        "components": [
                            {
                                "selector": "ligand",
                                "representation": "surface",
                                "focus": True,
                            }
                        ],
                    },
                },
            ],
        },
    }


def test_story_is_one_native_document_with_timing_and_roundtrip():
    data = build_mvs_story(story_input())
    assert data["mvsj"]["kind"] == "multiple"
    snapshots = data["mvsj"]["snapshots"]
    assert [s["metadata"]["key"] for s in snapshots] == ["overview", "ligand"]
    assert snapshots[0]["metadata"]["duration_ms"] == 6500
    assert snapshots[1]["metadata"]["duration_ms"] == 0
    assert snapshots[1]["metadata"]["transition_duration_ms"] == 0
    again = build_mvs_story({"story": data["story"]})
    assert again["mvsj"]["snapshots"] == snapshots


@pytest.mark.parametrize(
    "change", ["single", "duplicate", "unsupported", "negative", "boolean"]
)
def test_story_validation_rejects_ambiguous_or_invalid_scenes(change):
    data = story_input()
    scenes = data["story"]["scenes"]
    if change == "single":
        scenes.pop()
    elif change == "duplicate":
        scenes[1]["id"] = scenes[0]["id"]
    elif change == "unsupported":
        scenes[1]["builder"]["primitives"] = [{"type": "arrow"}]
    elif change == "negative":
        scenes[1]["duration_ms"] = -1
    else:
        scenes[1]["duration_ms"] = True
    with pytest.raises(ValueError):
        build_mvs_story(data)


def test_shared_story_matches_python_compiler():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/mvs_story.json").read_text()
    )
    assert (
        build_mvs_story(fixture["input"])["mvsj"]["snapshots"]
        == fixture["mvsj"]["snapshots"]
    )


@pytest.mark.parametrize(
    "representation",
    [
        {"type": "backbone", "size_factor": 1.4},
        {"type": "line", "ignore_hydrogens": True},
        {"type": "putty", "size_theme": "uncertainty", "size_factor": 2},
        {"type": "cartoon", "tubular_helices": True},
        {"type": "surface", "surface_type": "gaussian", "ignore_hydrogens": True},
    ],
)
def test_extended_representation_parameters_are_preserved(representation):
    result = compile_scene(components=[{"representation": representation}])
    assert next(nodes(result["mvsj"], "representation"))["params"] == representation
    assert (
        build_mvs({"builder": result["builder"]})["mvsj"]["root"]
        == result["mvsj"]["root"]
    )


@pytest.mark.parametrize(
    "clip",
    [
        {"type": "sphere", "center": [0, 0, 0], "radius": 5},
        {"type": "plane", "point": [0, 0, 0], "normal": [0, 1, 0]},
        {
            "type": "box",
            "center": [0, 0, 0],
            "size": [10, 20, 30],
            "invert": True,
            "variant": "object",
        },
    ],
)
def test_clipping_is_a_child_node_and_preserves_box_common_fields(clip):
    result = compile_scene(
        components=[
            {"representation": {"type": "surface", "clip": clip, "opacity": 0.5}}
        ]
    )
    rep = next(nodes(result["mvsj"], "representation"))
    assert rep["params"] == {"type": "surface"}
    assert next(nodes(rep, "clip"))["params"] == {
        "invert": False,
        "variant": "pixel",
        **clip,
    }
    assert next(nodes(rep, "opacity"))["params"] == {"opacity": 0.5}


def test_density_uses_its_parse_format_channel_mesh_and_evidence_source():
    volume = {
        "url": "https://ftp.wwpdb.org/pub/test.map",
        "channel_id": "2FOFCWT",
        "color": "blue",
        "opacity": 0.4,
        "representation": {"absolute_isovalue": 0.8, "show_wireframe": True},
    }
    result = compile_scene(volumes=[volume])
    assert list(nodes(result["mvsj"], "parse"))[-1]["params"]["format"] == "map"
    assert next(nodes(result["mvsj"], "volume"))["params"]["channel_id"] == "2FOFCWT"
    rep = next(nodes(result["mvsj"], "volume_representation"))
    assert rep["params"]["absolute_isovalue"] == 0.8
    assert rep["params"]["show_wireframe"] is True
    assert next(nodes(rep, "opacity"))["params"]["opacity"] == 0.4
    assert volume["url"] in result["sources"]
    assert result["legend"][-1]["representation"] == "isosurface"


@pytest.mark.parametrize(
    "fields",
    [
        {
            "components": [
                {"representation": {"type": "cartoon", "size_theme": "uncertainty"}}
            ]
        },
        {
            "components": [
                {"representation": {"type": "surface", "tubular_helices": True}}
            ]
        },
        {
            "components": [
                {
                    "representation": {
                        "type": "surface",
                        "clip": {
                            "type": "plane",
                            "point": [0, 0, 0],
                            "normal": [0, 0, 0],
                        },
                    }
                }
            ]
        },
        {
            "components": [
                {
                    "representation": {
                        "type": "surface",
                        "clip": {"type": "sphere", "center": [0, 0, 0], "radius": -1},
                    }
                }
            ]
        },
        {
            "components": [
                {
                    "representation": {
                        "type": "surface",
                        "clip": {"type": "box", "center": [0, 0, 0], "size": [1, 0, 1]},
                    }
                }
            ]
        },
        {"volumes": [{"url": "https://ebi.ac.uk.evil.test/map"}]},
        {"volumes": [{"url": "https://user@www.ebi.ac.uk/map"}]},
        {"volumes": [{"url": "https://www.ebi.ac.uk:8443/map"}]},
        {
            "volumes": [
                {
                    "url": "https://www.ebi.ac.uk/map",
                    "representation": {"absolute_isovalue": 1, "relative_isovalue": 1},
                }
            ]
        },
        {"structure": {"url": "https://www.ebi.ac.uk/a.pqr", "format": "pqr"}},
    ],
)
def test_new_features_reject_invalid_geometry_options_and_density_origins(fields):
    with pytest.raises(ValueError):
        compile_scene(**fields)


def test_story_transition_and_markdown_survive_replacement_roundtrip():
    spec = story_input()
    spec["story"]["description_format"] = "markdown"
    second = spec["story"]["scenes"][1]
    second["description"] = "**Ligand context**"
    second["description_format"] = "markdown"
    second["transition"] = {
        "duration_ms": 2000,
        "trajectory": "leap",
        "easing": "sin-in-out",
    }
    second.pop("transition_duration_ms", None)
    result = build_mvs_story(spec)
    snapshot = result["mvsj"]["snapshots"][1]
    assert next(nodes(snapshot, "transition"))["params"] == second["transition"]
    assert snapshot["metadata"]["transition_duration_ms"] == 2000
    assert snapshot["metadata"]["description_format"] == "markdown"
    assert result["mvsj"]["metadata"]["description_format"] == "markdown"
    assert (
        build_mvs_story({"story": result["story"]})["mvsj"]["snapshots"]
        == result["mvsj"]["snapshots"]
    )


@pytest.mark.parametrize(
    "builder",
    [
        {"entry_id": "1CBS"},
        {"pdbId": "1CBS"},
        {"structure": {"entryId": "1CBS"}},
        {
            "structure": {
                "url": "https://www.ebi.ac.uk/pdbe/entry-files/download/1CBS.bcif"
            }
        },
    ],
)
def test_entry_aliases_and_coordinate_filename_normalize_without_mutation(builder):
    original = deepcopy(builder)
    result = build_mvs({"builder": builder})
    assert result["builder"]["pdb_id"] == "1cbs"
    assert "entry_id" not in result["builder"]
    assert builder == original
    assert (
        build_mvs({"builder": result["builder"]})["mvsj"]["root"]
        == result["mvsj"]["root"]
    )


def test_legacy_styling_water_and_singular_component_normalize():
    result = compile_scene(
        show_water=True,
        component={
            "selector": " WATER ",
            "representation": " Space_Fill ",
            "color": {"value": " Blue "},
        },
    )
    assert result["builder"]["include_water"] is True
    assert result["builder"]["components"][0]["selector"] == "water"
    assert (
        next(nodes(result["mvsj"], "representation"))["params"]["type"] == "spacefill"
    )
    assert next(nodes(result["mvsj"], "color"))["params"]["color"] == "blue"
    assert (
        "component" not in result["builder"] and "show_water" not in result["builder"]
    )


def test_empty_components_and_default_assembly_restore_old_defaults():
    result = compile_scene(components=[], structure={"type": " ASSEMBLY "})
    assert result["builder"]["components"][0]["selector"] == "polymer"
    structure = next(nodes(result["mvsj"], "structure"))["params"]
    assert structure["type"] == "assembly"
    assert structure.get("assembly_id") is None  # Mol* chooses; do not fabricate an ID.


@pytest.mark.parametrize(
    "builder",
    [
        {"pdb_id": "1cbs", "entry_id": "4hhb"},
        {"pdb_id": "1cbs", "structure": {"entry_id": "4hhb"}},
        {"include_water": False, "show_water": True},
        {"components": [{"color": {"color": "blue", "value": "red"}}]},
        {"components": [{"representation": "UNKNOWN"}]},
        {"component": {}, "components": [{"selector": "protein"}]},
    ],
)
def test_compatibility_never_discards_conflicts_or_unknown_representations(builder):
    with pytest.raises(ValueError):
        compile_scene(**builder)


def test_story_optional_ids_titles_and_duration_alias_are_canonicalized():
    data = story_input()
    for item in data["story"]["scenes"]:
        item.pop("id")
        item.pop("title")
    data["story"]["scenes"][0]["linger_duration_ms"] = 4000
    result = build_mvs_story(data)
    assert result["story"]["scenes"][0]["id"] == "scene-1"
    assert result["story"]["scenes"][1]["title"] == "Scene 2"
    assert result["mvsj"]["snapshots"][0]["metadata"]["duration_ms"] == 4000
