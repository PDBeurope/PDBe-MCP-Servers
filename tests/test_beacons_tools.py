import json
from unittest.mock import Mock, patch

import mcp.types as types
import pytest
import requests

from pdbe_mcp_server import beacons_tools as beacons_module
from pdbe_mcp_server.beacons_tools import (
    ANNOTATION_PROVIDERS,
    FEATURE_TYPES,
    PROVIDERS,
    TOOL_ANNOTATIONS,
    TOOL_ENSEMBL_SUMMARY,
    TOOL_SEQUENCE,
    TOOL_UNIPROT_SUMMARY,
    beacons_tools,
    call_beacons_tool,
)
from pdbe_mcp_server.execution import ToolDeadlineExceeded

BASE = "https://www.ebi.ac.uk/pdbe/pdbe-kb/3dbeacons/api/v2/"


def _structure(provider, category="TEMPLATE-BASED"):
    return {"summary": {"provider": provider, "model_category": category}}


def _uniprot_summary(accession="P38398"):
    return {
        "uniprot_entry": {"ac": accession},
        "structures": [
            _structure("PDBe", "EXPERIMENTALLY DETERMINED"),
            _structure("AlphaFold DB", "AB-INITIO"),
            _structure("SWISS-MODEL"),
        ],
    }


@pytest.fixture
def budget(monkeypatch):
    """Stand in for the per-tool deadline with a configurable budget."""
    state = {"left": 40.0}
    monkeypatch.setattr(beacons_module, "remaining_seconds", lambda: state["left"])
    monkeypatch.setattr(beacons_module.time, "sleep", lambda seconds: None)
    return state


def _tool(name):
    return next(tool for tool in beacons_tools() if tool.name == name)


def test_tools_expose_strict_enums_and_required_fields():
    tools = {tool.name: tool for tool in beacons_tools()}
    assert set(tools) == {
        TOOL_UNIPROT_SUMMARY,
        TOOL_ENSEMBL_SUMMARY,
        TOOL_SEQUENCE,
        TOOL_ANNOTATIONS,
    }
    uniprot = tools[TOOL_UNIPROT_SUMMARY].inputSchema
    assert uniprot["properties"]["provider"]["enum"] == list(PROVIDERS)
    assert uniprot["properties"]["exclude_provider"]["enum"] == list(PROVIDERS)
    assert uniprot["required"] == ["accessions"]
    assert uniprot["additionalProperties"] is False
    annotations = tools[TOOL_ANNOTATIONS].inputSchema
    assert annotations["properties"]["type"]["enum"] == list(FEATURE_TYPES)
    assert annotations["properties"]["provider"]["enum"] == list(ANNOTATION_PROVIDERS)
    assert annotations["required"] == ["uniprot_accession", "type"]


@pytest.mark.parametrize(
    "name", [TOOL_UNIPROT_SUMMARY, TOOL_ENSEMBL_SUMMARY, TOOL_SEQUENCE]
)
def test_structure_tools_describe_pdbe_precedence(name):
    description = _tool(name).description
    assert "fallback" in description
    assert "provider 'pdbe'" in description
    assert "exclude_provider to 'pdbe'" in description
    assert "not as experimental" in description


@patch("pdbe_mcp_server.beacons_tools.HTTPClient.post")
def test_uniprot_summary_posts_body_and_forwards_filters(post, monkeypatch):
    monkeypatch.setenv("TOON_ENABLED", "false")
    post.return_value = [_uniprot_summary()]
    call_beacons_tool(
        TOOL_UNIPROT_SUMMARY,
        {"accessions": ["P38398"], "exclude_provider": "pdbe"},
    )
    assert post.call_args.args[0] == BASE + "uniprot/summary"
    assert post.call_args.kwargs["json"] == {
        "accessions": ["P38398"],
        "exclude_provider": "pdbe",
    }
    assert post.call_args.kwargs["max_retries"] == 2


def test_uniprot_summary_returns_envelope(monkeypatch):
    monkeypatch.setenv("TOON_ENABLED", "false")
    with patch(
        "pdbe_mcp_server.beacons_tools.HTTPClient.post",
        return_value=[_uniprot_summary()],
    ):
        text = call_beacons_tool(TOOL_UNIPROT_SUMMARY, {"accessions": ["P38398"]})
    envelope = json.loads(text)
    assert envelope["source"] == BASE + "uniprot/summary"
    assert envelope["parameters"] == {"accessions": ["P38398"]}
    assert envelope["data"][0]["uniprot_entry"]["ac"] == "P38398"
    assert "retrieved_at" in envelope


def test_ensembl_summary_excludes_pdbe_and_alphafold_alias(monkeypatch):
    monkeypatch.setenv("TOON_ENABLED", "false")
    response = {
        "ensembl_id": "ENSG00000288864",
        "uniprot_mappings": [
            {
                "uniprot_accession": {
                    "structures": [
                        _structure("PDBe", "EXPERIMENTALLY DETERMINED"),
                        _structure("AlphaFold DB", "AB-INITIO"),
                        _structure("SWISS-MODEL"),
                    ]
                }
            }
        ],
    }
    with patch(
        "pdbe_mcp_server.beacons_tools.HTTPClient.get", return_value=response
    ) as get:
        text = call_beacons_tool(
            TOOL_ENSEMBL_SUMMARY,
            {"ensembl_id": "ENSG00000288864", "exclude_provider": "pdbe"},
        )
    assert get.call_args.args[0] == BASE + "ensembl/summary/ENSG00000288864.json"
    providers = [
        s["summary"]["provider"]
        for s in json.loads(text)["data"]["uniprot_mappings"][0]["uniprot_accession"][
            "structures"
        ]
    ]
    assert providers == ["AlphaFold DB", "SWISS-MODEL"]


def test_ensembl_summary_forwards_provider_to_server(monkeypatch):
    monkeypatch.setenv("TOON_ENABLED", "false")
    with patch("pdbe_mcp_server.beacons_tools.HTTPClient.get", return_value={}) as get:
        call_beacons_tool(
            TOOL_ENSEMBL_SUMMARY, {"ensembl_id": "ENSG1", "provider": "pdbe"}
        )
    assert get.call_args.kwargs["params"] == {"provider": "pdbe"}


def test_annotations_exclude_maps_to_the_other_source(monkeypatch):
    monkeypatch.setenv("TOON_ENABLED", "false")
    with patch("pdbe_mcp_server.beacons_tools.HTTPClient.get", return_value={}) as get:
        call_beacons_tool(
            TOOL_ANNOTATIONS,
            {
                "uniprot_accession": "Q14676",
                "type": "DOMAIN",
                "exclude_provider": "pdbe",
            },
        )
    assert get.call_args.args[0] == BASE + "annotations/Q14676.json"
    assert get.call_args.kwargs["params"] == {"type": "DOMAIN", "provider": "alphafold"}


def test_annotations_rejects_provider_and_exclude_together():
    text = call_beacons_tool(
        TOOL_ANNOTATIONS,
        {
            "uniprot_accession": "Q14676",
            "type": "DOMAIN",
            "provider": "pdbe",
            "exclude_provider": "alphafold",
        },
    )
    assert text.startswith("Error: Use either provider or exclude_provider")


def test_sequence_submit_polls_until_results_arrive(budget):
    responses = [{"message": "Search in progress"}, [_uniprot_summary()]]
    with (
        patch(
            "pdbe_mcp_server.beacons_tools.HTTPClient.post",
            return_value={"job_id": "job-1"},
        ) as post,
        patch(
            "pdbe_mcp_server.beacons_tools.HTTPClient.get", side_effect=responses
        ) as get,
    ):
        text = call_beacons_tool(TOOL_SEQUENCE, {"action": "submit", "sequence": "MKV"})
    assert post.call_args.kwargs["json"] == {"sequence": "MKV"}
    assert get.call_count == 2
    assert get.call_args.kwargs["params"] == {"job_id": "job-1"}
    assert "complete" in text and "job-1" in text


def test_sequence_submit_returns_job_id_when_budget_runs_out(budget):
    budget["left"] = 3.0
    with (
        patch(
            "pdbe_mcp_server.beacons_tools.HTTPClient.post",
            return_value={"job_id": "job-2"},
        ),
        patch(
            "pdbe_mcp_server.beacons_tools.HTTPClient.get",
            return_value={"message": "Search in progress"},
        ) as get,
    ):
        text = call_beacons_tool(TOOL_SEQUENCE, {"action": "submit", "sequence": "MKV"})
    assert get.call_count == 1
    assert "in_progress" in text and "job-2" in text


def test_sequence_result_returns_partial_job_when_deadline_hits_mid_request(budget):
    with patch(
        "pdbe_mcp_server.beacons_tools.HTTPClient.get",
        side_effect=ToolDeadlineExceeded("deadline"),
    ):
        budget["left"] = 0.0
        text = call_beacons_tool(TOOL_SEQUENCE, {"action": "result", "job_id": "job-3"})
    assert "in_progress" in text and "job-3" in text


def test_sequence_result_filters_provider_in_each_result(budget, monkeypatch):
    monkeypatch.setenv("TOON_ENABLED", "false")
    accession = {"accession": "P38398", "summary": _uniprot_summary()}
    with patch(
        "pdbe_mcp_server.beacons_tools.HTTPClient.get", return_value=[accession]
    ):
        text = call_beacons_tool(
            TOOL_SEQUENCE,
            {"action": "result", "job_id": "job-4", "exclude_provider": "pdbe"},
        )
    providers = [
        s["summary"]["provider"]
        for s in json.loads(text)["data"]["results"][0]["summary"]["structures"]
    ]
    assert "PDBe" not in providers
    assert providers == ["AlphaFold DB", "SWISS-MODEL"]


@pytest.mark.parametrize(
    "arguments,message",
    [
        ({"action": "submit"}, "'sequence' is required"),
        (
            {"action": "submit", "sequence": "MKV", "job_id": "x"},
            "'job_id' is not used",
        ),
        ({"action": "result"}, "'job_id' is required"),
        (
            {"action": "result", "job_id": "x", "sequence": "MKV"},
            "'sequence' is not used",
        ),
        ({"action": "summary"}, "Action 'summary' needs"),
        ({"action": "summary", "sequence": "MKV", "id": "abc"}, "not both"),
        (
            {"action": "summary", "sequence": "MKV", "id_type": "md5"},
            "'id_type' is not used",
        ),
    ],
)
def test_sequence_rejects_mismatched_arguments(arguments, message):
    text = call_beacons_tool(TOOL_SEQUENCE, arguments)
    assert text.startswith("Error:") and message in text


def test_sequence_summary_accepts_sequence(monkeypatch):
    monkeypatch.setenv("TOON_ENABLED", "false")
    with patch("pdbe_mcp_server.beacons_tools.HTTPClient.get", return_value={}) as get:
        call_beacons_tool(TOOL_SEQUENCE, {"action": "summary", "sequence": "MKV"})
    assert get.call_args.args[0] == BASE + "sequence/summary"
    assert get.call_args.kwargs["params"] == {"id": "MKV", "type": "sequence"}


def test_sequence_summary_accepts_checksum(monkeypatch):
    monkeypatch.setenv("TOON_ENABLED", "false")
    with patch("pdbe_mcp_server.beacons_tools.HTTPClient.get", return_value={}) as get:
        call_beacons_tool(
            TOOL_SEQUENCE,
            {"action": "summary", "id": "5F9BA1D4C7DE6925", "id_type": "crc64"},
        )
    assert get.call_args.kwargs["params"] == {"id": "5F9BA1D4C7DE6925", "type": "crc64"}


def test_http_400_on_unknown_job_gives_actionable_message():
    response = Mock(status_code=400)
    error = requests.HTTPError(response=response)
    with patch("pdbe_mcp_server.beacons_tools.HTTPClient.get", side_effect=error):
        text = call_beacons_tool(TOOL_SEQUENCE, {"action": "result", "job_id": "nope"})
    assert "HTTP 400" in text and "submit the sequence again" in text


def test_deadline_exceeded_propagates_from_dispatcher():
    with (
        patch(
            "pdbe_mcp_server.beacons_tools.HTTPClient.get",
            side_effect=ToolDeadlineExceeded("deadline"),
        ),
        pytest.raises(ToolDeadlineExceeded),
    ):
        call_beacons_tool(TOOL_ENSEMBL_SUMMARY, {"ensembl_id": "ENSG1"})


def test_toon_is_used_when_enabled_and_json_when_disabled(monkeypatch):
    with (
        patch("pdbe_mcp_server.beacons_tools.HTTPClient.get", return_value={"a": 1}),
        patch("toon_format.encode", return_value="TOON_DATA") as encode,
    ):
        monkeypatch.setenv("TOON_ENABLED", "true")
        assert (
            call_beacons_tool(TOOL_ENSEMBL_SUMMARY, {"ensembl_id": "E"}) == "TOON_DATA"
        )
        encode.assert_called_once()
    with patch("pdbe_mcp_server.beacons_tools.HTTPClient.get", return_value={"a": 1}):
        monkeypatch.setenv("TOON_ENABLED", "false")
        text = call_beacons_tool(TOOL_ENSEMBL_SUMMARY, {"ensembl_id": "E"})
    assert json.loads(text)["data"] == {"a": 1}


@pytest.mark.asyncio
async def test_api_server_routes_beacons_tools_by_public_name(
    mock_openapi_spec, monkeypatch
):
    from pdbe_mcp_server.api_tools import OpenAPIToMCPGenerator
    from pdbe_mcp_server.server import build_pdbe_api_server

    monkeypatch.setenv("TOON_ENABLED", "false")
    generator = OpenAPIToMCPGenerator("https://example.test/openapi.json")
    generator.openapi_spec = mock_openapi_spec
    server = build_pdbe_api_server(generator)
    handler = server.request_handlers[types.CallToolRequest]

    def request(arguments):
        return types.CallToolRequest(
            params=types.CallToolRequestParams(
                name="ebi-pdbe-3dbeacons_ensembl_summary", arguments=arguments
            )
        )

    with patch(
        "pdbe_mcp_server.beacons_tools.HTTPClient.get",
        return_value={"ensembl_id": "ENSG1", "uniprot_mappings": []},
    ) as get:
        result = (await handler(request({"ensembl_id": "ENSG1"}))).root
    assert not result.isError
    assert "ENSG1" in result.content[0].text
    get.assert_called_once()

    invalid = (await handler(request({"ensembl_id": "ENSG1", "provider": "nope"}))).root
    assert invalid.isError
    assert "Input validation error" in invalid.content[0].text


def test_blank_optional_values_are_dropped_before_validation():
    from pdbe_mcp_server.beacons_tools import normalize_arguments

    assert normalize_arguments(
        {
            "action": "result",
            "job_id": "abc",
            "sequence": "",
            "id": None,
            "exclude_provider": "",
        }
    ) == {"action": "result", "job_id": "abc"}


@pytest.mark.asyncio
@pytest.mark.parametrize("aggregate", [False, True])
async def test_sequence_result_accepts_blank_unused_fields(
    mock_openapi_spec, monkeypatch, aggregate
):
    from pdbe_mcp_server.api_tools import OpenAPIToMCPGenerator
    from pdbe_mcp_server.server import build_all_server, build_pdbe_api_server

    monkeypatch.setenv("TOON_ENABLED", "false")
    generator = OpenAPIToMCPGenerator("https://example.test/openapi.json")
    generator.openapi_spec = mock_openapi_spec
    server = build_pdbe_api_server(generator)
    if aggregate:
        server = build_all_server([server])

    request = types.CallToolRequest(
        params=types.CallToolRequestParams(
            name="ebi-pdbe-3dbeacons_sequence",
            arguments={
                "action": "result",
                "job_id": "some-job",
                "sequence": "",
                "id": "",
                "id_type": "",
                "exclude_provider": "",
            },
        )
    )
    with patch("pdbe_mcp_server.beacons_tools.HTTPClient.get", return_value=[]) as get:
        result = (await server.request_handlers[types.CallToolRequest](request)).root
    assert not result.isError, result.content[0].text
    assert get.call_args.kwargs["params"] == {"job_id": "some-job"}


@pytest.mark.parametrize(
    "name", [TOOL_UNIPROT_SUMMARY, TOOL_ENSEMBL_SUMMARY, TOOL_SEQUENCE]
)
def test_structure_tools_explain_how_to_view_models(name):
    description = _tool(name).description
    assert "molview-spec" in description
    assert "AlphaFold DB" in description


def test_pdbe_model_url_from_beacons_builds_in_the_viewer():
    from pdbe_mcp_server.mvs import build_mvs

    result = build_mvs(
        {
            "builder": {
                "pdb_id": "1gq4",
                "structure": {
                    "url": "https://www.ebi.ac.uk/pdbe/static/entry/1gq4_updated.cif",
                    "format": "MMCIF",
                },
            }
        }
    )
    text = json.dumps(result["mvsj"])
    assert "https://www.ebi.ac.uk/pdbe/static/entry/1gq4_updated.cif" in text
    assert result["builder"]["structure"]["format"] == "mmcif"
