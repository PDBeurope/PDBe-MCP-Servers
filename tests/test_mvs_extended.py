"""Expanded APIs must survive normalization, story composition and viewer validation."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import mcp.types as types
import pytest

from pdbe_mcp_server.apps import build_pdbe_apps_server
from pdbe_mcp_server.mvs import BuildMvsInput, build_mvs, build_mvs_story
from pdbe_mcp_server.server import build_all_server
from pdbe_mcp_server.skills import SkillCatalog

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/mvs_extended.json").read_text()
)


def nodes(node, kind):
    return ([node] if node.get("kind") == kind else []) + [
        item for child in node.get("children", []) for item in nodes(child, kind)
    ]


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f["name"])
def test_expanded_apis_match_viewer_fixtures_and_roundtrip(fixture):
    original = deepcopy(fixture["input"])
    result = build_mvs({"builder": original})
    assert original == fixture["input"]
    assert result["mvsj"]["root"] == fixture["mvsj"]["root"]
    assert (
        build_mvs({"builder": result["builder"]})["mvsj"]["root"]
        == result["mvsj"]["root"]
    )
    story = build_mvs_story(
        {
            "story": {
                "title": "Expanded APIs",
                "scenes": [
                    {"builder": original},
                    {"builder": {"pdb_id": "1cbs"}},
                ],
            }
        }
    )
    assert story["mvsj"]["snapshots"][0]["root"] == result["mvsj"]["root"]
    assert (
        build_mvs_story({"story": story["story"]})["mvsj"]["snapshots"]
        == story["mvsj"]["snapshots"]
    )


def test_all_coordinate_and_annotation_sources_are_retained():
    result = build_mvs({"builder": FIXTURES[0]["input"]})
    assert set(result["sources"]) == {
        "https://www.ebi.ac.uk/pdbe/entry-files/download/1cbs.bcif",
        "https://www.ebi.ac.uk/pdbe/entry-files/download/1abc.bcif",
    }
    result = build_mvs({"builder": FIXTURES[1]["input"]})
    assert "https://www.ebi.ac.uk/annotations.json" in result["sources"]
    assert result["legend"][0]["label"] == "Annotated site"
    assert len(nodes(result["mvsj"]["root"], "color_from_uri")) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"structure": {"transform": {"rotation": [1] * 9}}},
        {"structure": {"transform": {"translation": [1, 2]}}},
        {"structure": {"transform": {"matrix": [1] * 16}}},
        {"structure": {"transform": {"matrix": [1] * 16, "translation": [1, 2, 3]}}},
        {"structure": {"instances": [{}]}},
        {
            "structure": {"ref": "same"},
            "additional_structures": [{"pdb_id": "1abc", "structure": {"ref": "same"}}],
        },
        {"primitives": [{"type": "sphere", "center": [0, 0, 0], "radius": -1}]},
        {
            "primitives": [
                {
                    "type": "sphere",
                    "center": {
                        "expressions": [{"label_asym_id": "A"}],
                        "structure_ref": "missing",
                    },
                }
            ]
        },
        {"primitives": [{"type": "arrow", "start": [0, 0, 0]}]},
        {"primitives": [{"type": "arrow", "start": [0, 0, 0], "direction": [0, 0, 0]}]},
        {
            "primitives": [
                {"type": "mesh", "vertices": [0, 0, 0] * 3, "indices": [0, 1, 3]}
            ]
        },
        {
            "primitives": [
                {"type": "lines", "vertices": [0, 0, 0] * 2, "indices": [0, 1, 1]}
            ]
        },
        {
            "primitives": [
                {
                    "type": "ellipse",
                    "center": [0, 0, 0],
                    "major_axis": [1, 0, 0],
                    "minor_axis": [2, 0, 0],
                }
            ]
        },
        {
            "primitives": [
                {
                    "type": "ellipsoid",
                    "center": [0, 0, 0],
                    "radius": 1,
                    "major_axis": [0, 0, 0],
                }
            ]
        },
        {
            "components": [
                {
                    "annotation": {
                        "schema": "residue",
                        "uri": "https://evil.test/a.json",
                        "format": "json",
                    }
                }
            ]
        },
        {
            "components": [
                {
                    "annotation": {
                        "schema": "residue",
                        "uri": "https://www.ebi.ac.uk/a.json",
                    }
                }
            ]
        },
        {"components": [{"annotation": {"schema": "residue"}}]},
        {
            "components": [
                {
                    "selector": "polymer",
                    "annotation": {"schema": "residue", "category_name": "site"},
                }
            ]
        },
        {
            "structure": {"format": "pdb", "url": "https://www.ebi.ac.uk/a.pdb"},
            "labels_from": [{"schema": "residue", "category_name": "site"}],
        },
        {"components": [{"selector": {"molql": {"head": {"name": "not-a-symbol"}}}}]},
        {
            "components": [
                {
                    "selector": {
                        "molql": {"head": {"name": "core.rel.eq"}, "args": [1, 1]}
                    }
                }
            ]
        },
        {
            "components": [
                {
                    "selector": {
                        "molql": {
                            "head": {"name": "structure-query.generator.atom-groups"},
                            "args": {"made-up": 1},
                        }
                    }
                }
            ]
        },
        {
            "annotations": [
                {
                    "selector": {
                        "molql": {"head": {"name": "structure-query.generator.all"}}
                    },
                    "group_id": "site",
                    "label": "Site",
                }
            ]
        },
    ],
)
def test_invalid_extended_inputs_fail_before_viewer_load(change):
    with pytest.raises(ValueError):
        build_mvs({"builder": {"pdb_id": "1cbs", **change}})


def test_remote_schema_exposes_extended_fields():
    schema = BuildMvsInput.model_json_schema()
    for name in (
        "Transform",
        "MolQL",
        "AnnotationData",
        "Sphere",
        "Distance",
        "Mesh",
        "StructureLayer",
    ):
        assert name in schema["$defs"]
    catalog = SkillCatalog()
    served = json.loads(
        catalog.read(catalog.root_uri + "/references/scene.schema.json")["text"]
    )
    assert served == schema


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f["name"])
@pytest.mark.parametrize("story", [False, True])
@pytest.mark.parametrize("aggregate", [False, True])
async def test_expanded_inputs_cross_mcp_schema_validation_and_app_delivery(
    fixture, story, aggregate
):
    child = build_pdbe_apps_server(Mock())
    server = build_all_server([child]) if aggregate else child
    arguments = (
        {"builder": fixture["input"]}
        if not story
        else {
            "story": {
                "title": "Expanded APIs",
                "scenes": [
                    {"builder": fixture["input"]},
                    {"builder": {"pdb_id": "1cbs"}},
                ],
            }
        }
    )
    result = (
        await server.request_handlers[types.CallToolRequest](
            types.CallToolRequest(
                params=types.CallToolRequestParams(
                    name="ebi-pdbe-build_mvs_story" if story else "ebi-pdbe-build_mvs",
                    arguments=arguments,
                ),
            )
        )
    ).root
    assert isinstance(result, types.CallToolResult)
    assert not result.isError, result
    assert result.structuredContent["status"] == "compiled"
    mvsj = result.meta["mvs"]["mvsj"]
    root = mvsj["snapshots"][0]["root"] if story else mvsj["root"]
    expected = json.loads(json.dumps(fixture["mvsj"]["root"]))
    structure_ids = iter(result.meta["workspace"]["scenes"][0]["structures"])

    def add_workspace_refs(node):
        if node["kind"] == "structure":
            node["ref"] = next(structure_ids)["id"]
        for child in node.get("children", []):
            add_workspace_refs(child)

    add_workspace_refs(expected)
    assert root == expected
    spec = (
        result.structuredContent["story"]
        if story
        else result.structuredContent["builder"]
    )
    assert spec
