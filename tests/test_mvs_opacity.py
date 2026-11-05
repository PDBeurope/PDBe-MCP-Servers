"""Recover misplaced transparency before MCP validation without changing intent."""

from copy import deepcopy
from unittest.mock import Mock

import mcp.types as types
import pytest

from pdbe_mcp_server.apps import build_pdbe_apps_server
from pdbe_mcp_server.mvs import BuildMvsInput, build_mvs, build_mvs_story
from pdbe_mcp_server.server import build_all_server


def nodes(node, kind):
    return ([node] if node.get("kind") == kind else []) + [
        item for child in node.get("children", []) for item in nodes(child, kind)
    ]


def arguments(*, story=False, annotation=False, **component):
    scene = {
        "pdb_id": "1cbs",
        "annotations" if annotation else "components": [
            {"selector": "polymer", **component},
        ],
    }
    return (
        {
            "story": {
                "title": "Opacity",
                "scenes": [
                    {"builder": {"pdb_id": "1cbs"}},
                    {"builder": scene},
                ],
            }
        }
        if story
        else {"builder": scene}
    )


@pytest.mark.parametrize(
    "representation",
    [None, "surface", {"type": "cartoon"}, {"type": "surface", "opacity": 0.25}],
)
@pytest.mark.parametrize("annotation", [False, True])
def test_component_opacity_normalizes_without_mutating_input(
    representation, annotation
):
    params = {"opacity": 0.25}
    if representation is not None:
        params["representation"] = representation
    spec = arguments(annotation=annotation, **params)
    original = deepcopy(spec)
    compiled = build_mvs(spec)
    assert spec == original
    item = compiled["builder"]["annotations" if annotation else "components"][0]
    assert "opacity" not in item
    assert item["representation"]["opacity"] == 0.25
    assert item["representation"]["type"] == (
        "surface"
        if representation == "surface"
        or isinstance(representation, dict)
        and representation["type"] == "surface"
        else "cartoon"
    )
    reps = nodes(compiled["mvsj"]["root"], "representation")
    target = reps[-1]
    assert "opacity" not in target["params"]
    assert nodes(target, "opacity")[0]["params"] == {"opacity": 0.25}
    assert (
        build_mvs({"builder": compiled["builder"]})["mvsj"]["root"]
        == compiled["mvsj"]["root"]
    )


@pytest.mark.parametrize("opacity", [0, 1, 0.5])
def test_opacity_alias_works_on_additional_structure_layers(opacity):
    compiled = build_mvs(
        {
            "builder": {
                "pdb_id": "1cbs",
                "additional_structures": [
                    {
                        "pdb_id": "4hhb",
                        "components": [{"selector": "polymer", "opacity": opacity}],
                    },
                ],
            }
        }
    )
    item = compiled["builder"]["additional_structures"][0]["components"][0]
    assert item["representation"]["opacity"] == opacity


@pytest.mark.parametrize("opacity", [-0.1, 1.1, float("nan"), float("inf")])
def test_normalization_does_not_hide_invalid_opacity(opacity):
    with pytest.raises(ValueError):
        build_mvs(arguments(opacity=opacity))


@pytest.mark.parametrize("aggregate", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("story", [False, True])
@pytest.mark.parametrize("annotation", [False, True])
@pytest.mark.asyncio
async def test_opacity_alias_crosses_sdk_validation_on_every_builder_route(
    aggregate, legacy, story, annotation
):
    child = build_pdbe_apps_server(Mock())
    server = build_all_server([child]) if aggregate else child
    tool = ("pdbe_build_mvs" if legacy else "ebi-pdbe-build_mvs") + (
        "_story" if story else ""
    )
    spec = arguments(
        story=story, annotation=annotation, opacity=0.3, representation="cartoon"
    )
    original = deepcopy(spec)
    result = (
        await server.request_handlers[types.CallToolRequest](
            types.CallToolRequest(
                params=types.CallToolRequestParams(name=tool, arguments=spec),
            )
        )
    ).root
    assert not result.isError, result
    assert result.structuredContent["status"] == "compiled"
    scene = (
        result.structuredContent["story"]["scenes"][1]["builder"]
        if story
        else result.structuredContent["builder"]
    )
    item = scene["annotations" if annotation else "components"][0]
    assert "opacity" not in item
    assert item["representation"]["opacity"] == 0.3
    mvsj = result.meta["mvs"]["mvsj"]
    root = mvsj["snapshots"][1]["root"] if story else mvsj["root"]
    assert nodes(root, "opacity")[-1]["params"] == {"opacity": 0.3}
    assert spec == original
    if story:
        assert (
            build_mvs_story({"story": result.structuredContent["story"]})["mvsj"][
                "snapshots"
            ]
            == mvsj["snapshots"]
        )


@pytest.mark.parametrize("annotation", [False, True])
@pytest.mark.parametrize("problem", ["conflict", "bounds"])
@pytest.mark.asyncio
async def test_bad_story_opacity_fails_before_compilation_with_correction_hint(
    monkeypatch, annotation, problem
):
    compiler = Mock(wraps=build_mvs_story)
    monkeypatch.setattr("pdbe_mcp_server.apps.build_mvs_story", compiler)
    spec = arguments(
        story=True,
        annotation=annotation,
        opacity=0.3 if problem == "conflict" else 1.5,
        representation={
            "type": "cartoon",
            **({"opacity": 0.7} if problem == "conflict" else {}),
        },
    )
    server = build_pdbe_apps_server(Mock())

    async def invoke():
        return (
            await server.request_handlers[types.CallToolRequest](
                types.CallToolRequest(
                    params=types.CallToolRequestParams(
                        name="ebi-pdbe-build_mvs_story", arguments=spec
                    ),
                )
            )
        ).root

    failed = await invoke()
    assert failed.isError
    compiler.assert_not_called()
    issue = failed.structuredContent["issues"][0]
    field = f"story.scenes.1.builder.{'annotations' if annotation else 'components'}.0.representation.opacity"
    assert issue["field"] == field
    assert issue["suggested_field"] == field
    assert "0 (transparent) to 1 (opaque)" in issue["hint"]
    assert "Correction:" in failed.content[0].text
    assert not failed.meta
    item = spec["story"]["scenes"][1]["builder"][
        "annotations" if annotation else "components"
    ][0]
    item.pop("opacity")
    item["representation"]["opacity"] = 0.3
    fixed = await invoke()
    assert not fixed.isError, fixed
    compiler.assert_called_once()


def test_schema_keeps_opacity_in_representation_with_explicit_guidance():
    schema = BuildMvsInput.model_json_schema()
    for name in ("Component", "Annotation"):
        fields = schema["$defs"][name]["properties"]
        assert "opacity" not in fields
        assert "inside representation" in fields["representation"]["description"]
    assert (
        "components[].representation.opacity"
        in schema["$defs"]["Representation"]["properties"]["opacity"]["description"]
    )
