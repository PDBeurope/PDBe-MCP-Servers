"""Namespace discovery, legacy aliases, and SDK validation on real builders."""

import re
from unittest.mock import Mock

import mcp.types as types
import pytest

from pdbe_mcp_server.api_tools import OpenAPIToMCPGenerator
from pdbe_mcp_server.apps import build_pdbe_apps_server
from pdbe_mcp_server.graph_tools import GraphTools
from pdbe_mcp_server.server import (
    build_all_server,
    build_graph_server,
    build_pdbe_api_server,
    build_pdbe_search_server,
    search_tools,
)
from pdbe_mcp_server.tool_names import PDBeServer, public_tool_name


async def tools(server):
    return (
        await server.request_handlers[types.ListToolsRequest](types.ListToolsRequest())
    ).root.tools


async def call(server, name, arguments):
    request = types.CallToolRequest(
        params=types.CallToolRequestParams(name=name, arguments=arguments)
    )
    result = (await server.request_handlers[types.CallToolRequest](request)).root
    assert request.params.name == name, "Dispatch must not mutate the original request"
    return result


@pytest.fixture
def servers(monkeypatch, mock_openapi_spec):
    monkeypatch.setenv("NEO4J_ENABLED", "false")
    monkeypatch.setattr(
        GraphTools, "_get_graph_schema", lambda self: {"nodes": [], "edges": []}
    )
    monkeypatch.setattr(
        search_tools, "run_search_query", lambda arguments: "search results"
    )
    monkeypatch.setattr(search_tools, "get_search_schema", lambda: "schema")
    generator = OpenAPIToMCPGenerator("https://example.test/openapi.json")
    generator.openapi_spec = mock_openapi_spec
    generator._execute_request = Mock(return_value={"data": {"value": 7}})
    children = {
        "api": build_pdbe_api_server(generator),
        "search": build_pdbe_search_server(),
        "graph": build_graph_server(),
        "apps": build_pdbe_apps_server(generator),
    }
    return {**children, "all": build_all_server(list(children.values()))}, generator


@pytest.mark.asyncio
async def test_all_builders_advertise_only_unique_namespaced_tools(servers):
    endpoints, generator = servers
    child_names = set()
    for endpoint, server in endpoints.items():
        listed = await tools(server)
        names = {tool.name for tool in listed}
        assert len(names) == len(listed)
        assert all(
            name.startswith("ebi.pdbe.") and name.count("ebi.pdbe.") == 1
            for name in names
        )
        assert all(re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name) for name in names)
        if endpoint != "all":
            child_names.update(names)
        else:
            assert names == child_names
    generated_name = generator.list_tools()[0].name
    api_names = {tool.name for tool in await tools(endpoints["api"])}
    assert api_names == {"ebi.pdbe." + generated_name}
    assert {tool.name for tool in await tools(endpoints["apps"])} == {
        "ebi.pdbe.open_structure",
        "ebi.pdbe.compare_structures",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("aggregate", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "endpoint,old_name,arguments",
    [
        ("api", None, {"id": "one"}),
        ("search", "run_pdbe_search_query", {"query": "*:*"}),
        ("search", "get_pdbe_search_schema", {}),
        ("graph", "pdbe_graph_nodes", {}),
    ],
)
async def test_calls_work_before_listing_with_old_and_new_names(
    servers, aggregate, legacy, endpoint, old_name, arguments
):
    endpoints, generator = servers
    old_name = old_name or generator.list_tools()[0].name
    server = endpoints["all" if aggregate else endpoint]
    result = await call(
        server, old_name if legacy else public_tool_name(old_name), arguments
    )
    assert not result.isError, result
    assert result.content


@pytest.mark.asyncio
@pytest.mark.parametrize("aggregate", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "endpoint,old_name",
    [
        ("api", None),
        ("search", "run_pdbe_search_query"),
        ("apps", "pdbe_open_structure"),
        ("apps", "pdbe_compare_structures"),
    ],
)
async def test_legacy_aliases_do_not_bypass_input_validation(
    servers, aggregate, legacy, endpoint, old_name
):
    endpoints, generator = servers
    old_name = old_name or generator.list_tools()[0].name
    result = await call(
        endpoints["all" if aggregate else endpoint],
        old_name if legacy else public_tool_name(old_name),
        {},
    )
    assert result.isError
    assert "Input validation error" in result.content[0].text


@pytest.mark.asyncio
async def test_namespace_preserves_metadata_and_output_validation():
    server = PDBeServer("test")
    original = types.Tool(
        name="sample",
        inputSchema={"type": "object"},
        outputSchema={"type": "object", "required": ["value"]},
        annotations=types.ToolAnnotations(readOnlyHint=True),
        _meta={"ui": {"resourceUri": "ui://pdbe/test"}},
    )

    @server.list_tools()
    async def list_tools():
        return [original]

    @server.call_tool()
    async def execute(name, arguments):
        assert name == "sample"
        return {}

    published = (await tools(server))[0]
    assert published.model_dump(exclude={"name"}) == original.model_dump(
        exclude={"name"}
    )
    assert original.name == "sample"
    for name in ("sample", "ebi.pdbe.sample"):
        result = await call(server, name, {})
        assert result.isError
        assert "Output validation error" in result.content[0].text


@pytest.mark.asyncio
async def test_duplicate_canonical_names_are_rejected():
    server = PDBeServer("test")

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(name=name, inputSchema={})
            for name in ("pdbe_open_structure", "ebi.pdbe.open_structure")
        ]

    with pytest.raises(ValueError, match="Duplicate public tool name"):
        await tools(server)


def test_generated_suffix_stays_stable_and_short():
    generator = OpenAPIToMCPGenerator("https://example.test/openapi.json")
    shortened = generator._shorten_tool_name("long_operation_" * 30)
    name = public_tool_name(shortened)
    assert name == "ebi.pdbe." + shortened
    assert public_tool_name(name) == name
    assert len(name) <= 59


@pytest.mark.asyncio
async def test_request_aware_lists_preserve_pagination():
    server = PDBeServer("test")

    @server.list_tools()
    async def list_tools(request: types.ListToolsRequest):
        return types.ListToolsResult(
            tools=[types.Tool(name="sample", inputSchema={})], nextCursor="next"
        )

    result = (
        await server.request_handlers[types.ListToolsRequest](types.ListToolsRequest())
    ).root
    assert result.tools[0].name == "ebi.pdbe.sample"
    assert result.nextCursor == "next"


@pytest.mark.asyncio
async def test_other_namespaces_do_not_alias_pdbe_tools(servers):
    endpoints, generator = servers
    old_name = generator.list_tools()[0].name
    result = await call(endpoints["all"], "other.pdbe." + old_name, {"id": "one"})
    assert result.isError
    generator._execute_request.assert_not_called()
