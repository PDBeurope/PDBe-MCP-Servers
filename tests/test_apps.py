"""Scientific mapping and retrieval contracts for the Structure Explorer."""

import asyncio
from contextlib import AsyncExitStack
from unittest.mock import Mock, patch

import httpx
import mcp.types as types
import pytest
import requests
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

from pdbe_mcp_server import apps
from pdbe_mcp_server.apps import (
    APP_RESOURCES,
    build_pdbe_apps_server,
    get_structure_data,
    normalize_annotations,
)


def chain(label="X", author="A"):
    return {
        "entity_id": "1",
        "label_asym_id": label,
        "auth_asym_id": author,
        "residues": [
            {
                "label_seq_id": n,
                "auth_seq_id": n + 100,
                "insertion_code": "B" if n == 3 else "",
                "comp_id": "ALA",
            }
            for n in range(1, 11)
        ],
    }


def track(regions, source="InterPro", accession="IPR1"):
    return {
        "data": [
            {
                "name": "Domain",
                "accession": accession,
                "dataType": source,
                "additionalData": {"bestChainId": "A"},
                "residues": regions,
            }
        ]
    }


def test_discontinuous_domains_preserve_chain_and_sequence_numbering():
    regions = [
        {
            "startIndex": a,
            "endIndex": b,
            "indexType": "PDB",
            "additionalData": {"domainId": "IPR1", "domainName": "Domain"},
        }
        for a, b in [(1, 3), (7, 9)]
    ]
    warnings = []
    features = normalize_annotations(
        [("domains", "1", track(regions), "https://example.test/domains")],
        [chain(), chain("Y", "C")],
        [],
        warnings,
    )
    assert not warnings and len(features) == 1
    segments = features[0]["segments"]
    assert [(s["start"], s["end"]) for s in segments] == [(1, 3), (7, 9)]
    assert {s["label_asym_id"] for s in segments} == {"X"}


def test_uniprot_positions_require_explicit_sifts_correspondence():
    mappings = track(
        [
            {
                "startIndex": 1,
                "endIndex": 10,
                "unpStartIndex": 21,
                "unpEndIndex": 30,
                "indexType": "PDB",
            }
        ],
        "UniProt",
        "P12345",
    )
    annotations = track(
        [
            {
                "startIndex": 23,
                "endIndex": 24,
                "indexType": "UNIPROT",
                "additionalData": {"uniprotAccession": "P12345", "rawScore": 0.7},
            }
        ]
    )
    warnings = []
    features = normalize_annotations(
        [
            ("uniprot_mapping", "1", mappings, "sifts"),
            ("annotations", "1", annotations, "annotations"),
        ],
        [chain()],
        [],
        warnings,
    )
    feature = next(f for f in features if f["kind"] == "annotations")
    segment = feature["segments"][0]
    assert (segment["start"], segment["end"]) == (3, 4)
    assert segment["details"]["rawScore"] == 0.7
    assert not warnings


def test_unmappable_annotations_are_reported():
    warnings = []
    data = track([{"startIndex": 23, "endIndex": 24, "indexType": "UNIPROT"}])
    assert (
        normalize_annotations(
            [("annotations", "1", data, "source")], [chain()], [], warnings
        )
        == []
    )
    assert "Omitted 1" in warnings[0]


def test_binding_sites_follow_bound_molecule_chain():
    regions = [
        {
            "startIndex": 2,
            "endIndex": 2,
            "indexType": "PDB",
            "additionalData": {"boundMoleculeId": "bm2"},
        }
    ]
    ligands = [{"bound_molecule_id": "bm2", "auth_asym_id": "C"}]
    features = normalize_annotations(
        [("binding_sites", "1", track(regions), "source")],
        [chain(), chain("Y", "C")],
        ligands,
        [],
    )
    assert features[0]["segments"][0]["label_asym_id"] == "Y"


@pytest.mark.asyncio
async def test_app_reuses_raw_executor_and_handles_missing_annotations():
    executor = Mock()
    records = {
        "summary": [{"title": "Test", "assemblies": []}],
        "molecules": [
            {
                "entity_id": 1,
                "molecule_type": "polypeptide(L)",
                "sequence": "A",
                "molecule_name": ["Protein"],
                "in_chains": ["A"],
                "in_struct_asyms": ["X"],
            }
        ],
        "residue_listing": {
            "molecules": [
                {
                    "entity_id": 1,
                    "chains": [
                        {
                            "struct_asym_id": "X",
                            "chain_id": "A",
                            "residues": [
                                {
                                    "residue_number": 1,
                                    "residue_name": "ALA",
                                    "author_residue_number": -2,
                                    "author_insertion_code": "B",
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "ligand_monomers": [],
        "domains": track([{"startIndex": 1, "endIndex": 1, "indexType": "PDB"}]),
        "binding_sites": {"data": []},
        "uniprot_mapping": {"data": []},
    }

    def execute(method, path, arguments):
        assert method == "GET" and arguments["pdb_id"] == "1abc"
        endpoint = path.split("/")[3]
        if endpoint == "annotations":
            raise requests.ConnectionError("Annotation service unavailable")
        return {
            "data": {"1abc": records[endpoint]},
            "source": f"https://example.test/{endpoint}",
        }

    executor.execute_operation.side_effect = execute
    data = await get_structure_data({"pdb_id": "1ABC"}, executor)
    assert executor.execute_operation.call_count == 8
    assert data["annotations"][0]["segments"][0]["label_asym_id"] == "X"
    assert data["chains"][0]["residues"][0]["auth_seq_id"] == -2
    assert data["chains"][0]["residues"][0]["insertion_code"] == "B"
    assert any("annotations" in warning for warning in data["warnings"])


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def app_client(tmp_path, monkeypatch):
    """Exercise real HTTP request contexts and /all forwarding without PDBe I/O."""
    with patch(
        "pdbe_mcp_server.graph_tools.GraphTools._get_graph_schema",
        return_value={"nodes": [], "edges": []},
    ):
        from pdbe_mcp_server.server import build_all_server

    for name in ("UI_FILE", "COMPARISON_UI_FILE"):
        path = tmp_path / f"{name}.html"
        path.write_text(
            '<!doctype html><html lang="en"><head></head><body>'
            f'<main data-bundle="{name}"><header class="brand-header">PDBe</header>'
            '<section class="search-strip"><form></form></section>'
            '<div id="viewer"></div></main></body></html>',
            encoding="utf-8",
        )
        monkeypatch.setattr(apps, name, path)
    app_server = build_pdbe_apps_server(Mock())
    servers = {"apps": app_server, "all": build_all_server([app_server])}
    async with AsyncExitStack() as stack:
        routes = []
        for name, server in servers.items():
            manager = StreamableHTTPSessionManager(
                app=server, json_response=True, stateless=True
            )
            await stack.enter_async_context(manager.run())
            routes.append(Mount(f"/mcp/{name}", app=manager.handle_request))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=Starlette(routes=routes)),
            base_url="http://localhost",
            headers={
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-11-25",
            },
        ) as client:
            yield client


async def rpc(client, path, method, params=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    response = await client.post(path, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["apps", "all"])
@pytest.mark.parametrize(
    "query,header,search",
    [
        ("", True, True),
        ("?internal=false", True, True),
        ("?internal=TRUE", False, False),
        ("?show_header=false", False, True),
        ("?show_search=false", True, False),
        ("?internal=true&show_search=true", False, True),
        ("?internal=true&show_header=true", True, False),
        ("?internal=true&show_header=true&show_search=true", True, True),
    ],
)
async def test_display_preferences_over_http(
    app_client, endpoint, query, header, search
):
    path = f"/mcp/{endpoint}/{query}"
    tools = (await rpc(app_client, path, "tools/list"))["result"]["tools"]
    uris = {
        tool["_meta"]["ui"]["resourceUri"]
        for tool in tools
        if "resourceUri" in tool["_meta"]["ui"]
    }
    listed = (await rpc(app_client, path, "resources/list"))["result"]["resources"]
    assert uris == {item["uri"] for item in listed}
    assert len(uris) == 2
    assert (uris == set(APP_RESOURCES)) == (header and search)

    for uri in uris:
        # Read through an unconfigured connection: the URI determines the HTML.
        result = await rpc(
            app_client, f"/mcp/{endpoint}/", "resources/read", {"uri": uri}
        )
        resource = result["result"]["contents"][0]
        assert resource["uri"] == uri
        assert resource["mimeType"] == apps.APP_MIME_TYPE
        html = resource["text"]
        assert f'data-pdbe-show-header="{str(header).lower()}"' in html
        assert f'data-pdbe-show-search="{str(search).lower()}"' in html
        expected_bundle = (
            "COMPARISON_UI_FILE" if "structure-comparison" in uri else "UI_FILE"
        )
        assert f'data-bundle="{expected_bundle}"' in html
        assert '<div id="viewer">' in html
        assert resource["_meta"]["ui"]["csp"] == {
            "connectDomains": ["https://www.ebi.ac.uk"],
            "resourceDomains": ["data:", "blob:"],
        }


@pytest.mark.anyio
async def test_display_preferences_are_isolated_between_clients(app_client):
    paths = ["/mcp/all/?internal=true", "/mcp/all/", "/mcp/apps/?show_search=false"]
    results = await asyncio.gather(
        *(rpc(app_client, path, "tools/list") for path in paths * 2)
    )
    for index, result in enumerate(results):
        tool = next(
            tool
            for tool in result["result"]["tools"]
            if tool["name"] == "pdbe_open_structure"
        )
        suffix = [
            "?show_header=false&show_search=false",
            "",
            "?show_header=true&show_search=false",
        ][index % len(paths)]
        assert tool["_meta"]["ui"]["resourceUri"] == apps.RESOURCE_URI + suffix

    # A base URI must keep its original full UI even on an internal connection.
    result = await rpc(
        app_client, paths[0], "resources/read", {"uri": apps.RESOURCE_URI}
    )
    html = result["result"]["contents"][0]["text"]
    assert 'data-pdbe-show-header="true"' in html
    assert 'data-pdbe-show-search="true"' in html


@pytest.mark.asyncio
async def test_stdio_tools_keep_original_resource_uris():
    server = build_pdbe_apps_server(Mock())
    result = await server.request_handlers[types.ListToolsRequest](
        types.ListToolsRequest()
    )
    assert {
        tool.meta["ui"]["resourceUri"]
        for tool in result.root.tools
        if "resourceUri" in tool.meta["ui"]
    } == set(APP_RESOURCES)


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["apps", "all"])
async def test_removed_apps_are_unavailable(app_client, endpoint):
    path = f"/mcp/{endpoint}/?internal=true"
    tools = (await rpc(app_client, path, "tools/list"))["result"]["tools"]
    assert {tool["name"] for tool in tools} == {
        "pdbe_open_structure",
        "pdbe_compare_structures",
    }
    for name in (
        "pdbe_explore_ligand",
        "pdbe_get_ligand_contacts",
        "pdbe_sequence_coverage",
    ):
        response = await rpc(
            app_client, path, "tools/call", {"name": name, "arguments": {}}
        )
        assert response["result"]["isError"]
    for uri in ("ui://pdbe/ligand-explorer", "ui://pdbe/sequence-coverage"):
        response = await rpc(app_client, path, "resources/read", {"uri": uri})
        assert "Unknown resource" in response["error"]["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["apps", "all"])
async def test_invalid_display_options_are_reported(app_client, endpoint):
    response = await rpc(
        app_client, f"/mcp/{endpoint}/?show_header=invalid", "tools/list"
    )
    assert "show_header must be true or false" in response["error"]["message"]
    for suffix in (
        "?show_search=invalid",
        "?show_header=",
        "?unknown=false",
        "?show_header=true&show_header=false",
    ):
        response = await rpc(
            app_client,
            f"/mcp/{endpoint}/",
            "resources/read",
            {"uri": apps.RESOURCE_URI + suffix},
        )
        assert "error" in response
