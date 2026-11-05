from copy import deepcopy
from unittest.mock import Mock

import mcp.types as types
import pytest

from pdbe_mcp_server.apps import build_pdbe_apps_server
from pdbe_mcp_server.server import build_all_server


@pytest.mark.asyncio
@pytest.mark.parametrize("aggregate", [False, True])
@pytest.mark.parametrize("tool_name", ["ebi-pdbe-build_mvs", "pdbe_build_mvs"])
async def test_normalization_precedes_sdk_input_validation_on_both_routes(
    aggregate, tool_name
):
    child = build_pdbe_apps_server(Mock())
    server = build_all_server([child]) if aggregate else child
    arguments = {
        "builder": {
            "entry_id": "1CBS",
            "show_water": True,
            "component": {
                "selector": " WATER ",
                "representation": "Space_Fill",
                "color": {"value": "blue"},
            },
        }
    }
    original = deepcopy(arguments)
    result = (
        await server.request_handlers[types.CallToolRequest](
            types.CallToolRequest(
                params=types.CallToolRequestParams(name=tool_name, arguments=arguments),
            )
        )
    ).root
    assert isinstance(result, types.CallToolResult)
    assert not result.isError, result
    assert result.structuredContent["status"] == "compiled"
    assert result.structuredContent["builder"]["pdb_id"] == "1cbs"
    assert result.meta["mvs"]["mvsj"]["root"]["kind"] == "root"
    assert "not a placeholder" in result.content[0].text
    assert arguments == original


@pytest.mark.asyncio
@pytest.mark.parametrize("aggregate", [False, True])
async def test_validation_error_is_explicit_bounded_and_contains_no_raw_inputs(
    aggregate,
):
    child = build_pdbe_apps_server(Mock())
    server = build_all_server([child]) if aggregate else child
    result = (
        await server.request_handlers[types.CallToolRequest](
            types.CallToolRequest(
                params=types.CallToolRequestParams(
                    name="ebi-pdbe-build_mvs",
                    arguments={
                        "builder": {
                            "pdb_id": "1cbs",
                            "components": [
                                {"representation": "secret-not-a-representation"}
                            ],
                        }
                    },
                ),
            )
        )
    ).root
    assert result.isError
    assert result.structuredContent["status"] == "validation_failed"
    assert result.structuredContent["retryable"] is True
    assert result.structuredContent["issues"]
    text = result.content[0].text
    assert "secret-not-a-representation" not in text
    assert len(text) < 3500
    assert not result.meta


@pytest.mark.asyncio
@pytest.mark.parametrize("story", [False, True])
@pytest.mark.parametrize(
    "problem", ["missing_label", "mismatched_label", "named_selector"]
)
async def test_annotation_group_errors_identify_fields_and_can_be_corrected(
    story, problem
):
    annotations = [
        {
            "selector": {"label_asym_id": "A", "label_seq_id": seq},
            "group_id": "site",
            "label": "Binding site",
        }
        for seq in [10, 20]
    ]
    if problem == "missing_label":
        annotations[1].pop("label")
    elif problem == "mismatched_label":
        annotations[1]["label"] = "Different label"
    else:
        annotations[1]["selector"] = "ligand"
    scene = {"pdb_id": "1cbs", "annotations": annotations}
    arguments = (
        {
            "story": {
                "title": "Site",
                "scenes": [{"builder": scene}, {"builder": {"pdb_id": "1cbs"}}],
            }
        }
        if story
        else {"builder": scene}
    )
    server = build_pdbe_apps_server(Mock())

    async def invoke():
        return (
            await server.request_handlers[types.CallToolRequest](
                types.CallToolRequest(
                    params=types.CallToolRequestParams(
                        name="ebi-pdbe-build_mvs_story"
                        if story
                        else "ebi-pdbe-build_mvs",
                        arguments=arguments,
                    )
                )
            )
        ).root

    failed = await invoke()
    assert failed.isError
    field = "selector" if problem == "named_selector" else "label"
    prefix = "story.scenes.0." if story else ""
    assert (
        failed.structuredContent["issues"][0]["field"]
        == f"{prefix}builder.annotations.1.{field}"
    )
    annotations[1]["label"] = "Binding site"
    annotations[1]["selector"] = {"label_asym_id": "A", "label_seq_id": 20}
    fixed = await invoke()
    assert not fixed.isError, fixed
    assert fixed.structuredContent["status"] == "compiled"
