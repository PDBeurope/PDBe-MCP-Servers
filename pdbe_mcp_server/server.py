import os
from typing import Any, Callable, Sequence

import anyio
import click
import mcp.types as types
from mcp.server.lowlevel import Server
from omegaconf import DictConfig

from pdbe_mcp_server import get_config
from pdbe_mcp_server.api_tools import (
    OpenAPIToMCPGenerator,
    create_mcp_tools_from_openapi,
    get_shared_api_generator,
)
from pdbe_mcp_server.apps import app_resource_base_uri, build_pdbe_apps_server
from pdbe_mcp_server.execution import run_blocking_tool
from pdbe_mcp_server.graph_tools import GraphTools
from pdbe_mcp_server.search_tools import SearchTools
from pdbe_mcp_server.tool_names import PDBeServer

search_tools: SearchTools = SearchTools()

conf: DictConfig = get_config()

ROOT_PREFIX = os.getenv("ROOT_PREFIX", "")


class MCPServerFactory:
    """
    Factory class to create an MCP server instance.
    """

    def __init__(self) -> None:
        self._builders: dict[str, Callable[[], Server]] = {}

    def register(self, name: str, builder_func: Callable[[], Server]) -> None:
        self._builders[name] = builder_func

    def create(self, name: str) -> Server:
        if name not in self._builders:
            raise ValueError(f"No builder registered for {name}")
        return self._builders[name]()

    def available_types(self) -> list[str]:
        return list(self._builders.keys())


# Global factory instance
factory = MCPServerFactory()


def build_pdbe_api_server(generator: OpenAPIToMCPGenerator | None = None) -> Server:
    api_server = PDBeServer("pdbe-api-server")
    if generator is None:
        generator, available_tools = create_mcp_tools_from_openapi(conf.api.openapi_url)
    else:
        available_tools = generator.list_tools()

    @api_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return available_tools

    @api_server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if arguments is None:
            arguments = {}
        # These tools use requests (including synchronous retries). Keep the
        # entire operation, including response formatting, off the event loop.
        return await run_blocking_tool(generator.call_tool, name, arguments)

    return api_server


def build_graph_server(graph_tools: GraphTools | None = None) -> Server:
    # Construct explicitly at startup, never while importing this module.
    if graph_tools is None:
        graph_tools = GraphTools()
    graph_server = PDBeServer("pdbe-graph-server")

    @graph_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        tools = [
            graph_tools.get_pdbe_graph_nodes_tool(),
            graph_tools.get_pdbe_graph_edges_tool(),
            graph_tools.get_pdbe_graph_node_relationships_tool(),
            graph_tools.get_pdbe_graph_example_queries_tool(),
            graph_tools.get_pdbe_graph_indexes_tool(),
        ]

        # Add the cypher query tool only if Neo4j is configured
        from pdbe_mcp_server.graph_tools import _neo4j_enabled

        if _neo4j_enabled():
            tools.append(graph_tools.get_pdbe_run_cypher_query_tool())

        return tools

    @graph_server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if arguments is None:
            arguments = {}

        if name == "pdbe_graph_nodes":
            return [types.TextContent(text=graph_tools.format_nodes(), type="text")]
        elif name == "pdbe_graph_edges":
            return [types.TextContent(text=graph_tools.format_edges(), type="text")]
        elif name == "pdbe_graph_node_relationships":
            node_labels = arguments.get("node_labels", [])
            if not isinstance(node_labels, list):
                return [
                    types.TextContent(
                        type="text",
                        text="Error: node_labels parameter must be a list of strings",
                    )
                ]

            return [
                types.TextContent(
                    text=graph_tools.format_node_relationships(node_labels),
                    type="text",
                )
            ]
        elif name == "pdbe_graph_example_queries":
            return [
                types.TextContent(
                    text=graph_tools.format_example_queries(), type="text"
                )
            ]
        elif name == "pdbe_graph_indexes":
            return [types.TextContent(text=graph_tools.format_indexes(), type="text")]
        elif name == "pdbe_run_cypher_query":
            if not graph_tools:
                return [
                    types.TextContent(
                        type="text",
                        text="Cypher query tool not available: Neo4j configuration is missing",
                    )
                ]

            cypher_query = arguments.get("cypher_query", "")
            if not cypher_query:
                return [
                    types.TextContent(
                        type="text", text="Error: cypher_query parameter is required"
                    )
                ]

            try:
                result = await graph_tools.execute_cypher_query(cypher_query)
                return [types.TextContent(type="text", text=result)]
            except ValueError as e:
                return [types.TextContent(type="text", text=str(e))]
            except RuntimeError as e:
                return [types.TextContent(type="text", text=str(e))]
        else:
            raise ValueError(f"Unknown tool name: {name}")

    return graph_server


def build_pdbe_search_server() -> Server:
    search_server = PDBeServer(
        name="pdbe-search-server",
        instructions="""
You are a PDBe search assistant. You have access to tools that allow you to retrieve the Solr search schema
and execute search queries against the PDBe database. Use these tools to help users find relevant information
in the PDBe database. Always make sure to understand the search schema before constructing queries.
        """,
    )

    @search_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            search_tools.get_search_schema_tool(),
            search_tools.get_run_search_query_tool(),
        ]

    @search_server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if name == "get_pdbe_search_schema":
            schema = await run_blocking_tool(search_tools.get_search_schema)
            return [types.TextContent(type="text", text=schema)]
        elif name == "run_pdbe_search_query":
            return [
                types.TextContent(
                    type="text",
                    text=await run_blocking_tool(
                        search_tools.run_search_query, arguments
                    ),
                )
            ]
        else:
            raise ValueError(f"Unknown tool name: {name}")

    return search_server


def build_all_server(servers: Sequence[Server] | None = None) -> Server:
    """Build one MCP server that exposes the tools from every PDBe server."""
    if servers is None:
        generator = get_shared_api_generator()
        servers = [
            build_pdbe_api_server(generator),
            build_pdbe_search_server(),
            build_graph_server(),
            build_pdbe_apps_server(generator),
        ]

    all_server = PDBeServer("pdbe-all-server")
    tool_servers: dict[str, Server] = {}

    @all_server.list_resources()
    async def list_resources() -> list[types.Resource]:
        resources: list[types.Resource] = []
        seen: set[str] = set()
        for child in servers:
            handler = child.request_handlers.get(types.ListResourcesRequest)
            if handler is None:
                continue
            result = (await handler(types.ListResourcesRequest())).root
            if not isinstance(result, types.ListResourcesResult):
                raise RuntimeError(
                    f"Unexpected resources/list response from {child.name}"
                )
            for resource in result.resources:
                uri = str(resource.uri)
                if uri in seen:
                    raise ValueError(f"Duplicate resource URI in all server: {uri}")
                seen.add(uri)
                resources.append(resource)
        return resources

    # Forward complete results to preserve each resource's CSP and UI metadata.
    async def read_resource(request: types.ReadResourceRequest) -> types.ServerResult:
        uri = str(request.params.uri)
        app_base_uri = app_resource_base_uri(uri)
        owner: Server | None = None
        for child in servers:
            handler = child.request_handlers.get(types.ListResourcesRequest)
            if handler is None:
                continue
            result = (await handler(types.ListResourcesRequest())).root
            if isinstance(result, types.ListResourcesResult):
                if any(
                    str(resource.uri) == uri
                    or (
                        app_base_uri is not None
                        and app_resource_base_uri(str(resource.uri)) == app_base_uri
                    )
                    for resource in result.resources
                ):
                    if owner is not None:
                        raise ValueError(f"Duplicate resource URI in all server: {uri}")
                    owner = child
        if owner is None:
            raise ValueError(f"Unknown resource: {uri}")
        return await owner.request_handlers[types.ReadResourceRequest](request)

    all_server.request_handlers[types.ReadResourceRequest] = read_resource

    async def get_tools() -> list[types.Tool]:
        tools: list[types.Tool] = []
        owners: dict[str, Server] = {}

        for tool_server in servers:
            handler = tool_server.request_handlers[types.ListToolsRequest]
            result = await handler(types.ListToolsRequest())
            tool_result = result.root
            if not isinstance(tool_result, types.ListToolsResult):
                raise RuntimeError(
                    f"Unexpected tools/list response from {tool_server.name}"
                )

            for tool in tool_result.tools:
                if tool.name in owners:
                    raise ValueError(f"Duplicate tool name in all server: {tool.name}")
                owners[tool.name] = tool_server
                tools.append(tool)

        tool_servers.clear()
        tool_servers.update(owners)
        return tools

    @all_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return await get_tools()

    @all_server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        tool_server = tool_servers.get(name)
        if tool_server is None:
            # Ensure the owner map exists if a client calls a tool before listing.
            await get_tools()
            tool_server = tool_servers.get(name)
        if tool_server is None:
            raise ValueError(f"Unknown tool name: {name}")

        handler = tool_server.request_handlers[types.CallToolRequest]
        result = await handler(
            types.CallToolRequest(
                params=types.CallToolRequestParams(name=name, arguments=arguments)
            )
        )
        tool_result = result.root
        if not isinstance(tool_result, types.CallToolResult):
            raise RuntimeError(
                f"Unexpected tools/call response from {tool_server.name}"
            )
        return tool_result

    return all_server


factory.register("pdbe_graph_server", build_graph_server)
factory.register("pdbe_api_server", build_pdbe_api_server)
factory.register("pdbe_search_server", build_pdbe_search_server)
factory.register("pdbe_apps_server", build_pdbe_apps_server)


@click.command()
@click.option("--port", default=8000, help="Port to run the server on")
@click.option(
    "--transport",
    type=click.Choice(["sse", "stdio"]),
    default="stdio",
    help="Transport method for the MCP server",
)
@click.option(
    "--server-type",
    type=click.Choice(factory.available_types()),
    default="pdbe_api_server",
    help="Type of server to run",
)
def main(port: int, transport: str, server_type: str) -> int:
    try:
        server = factory.create(server_type)
    except ValueError as e:
        print(f"Error creating server: {e}")
        return 1

    if transport == "sse":
        import uvicorn
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.responses import Response
        from starlette.routing import Mount, Route

        sse = SseServerTransport("/messages/")

        root_paths = {
            "pdbe_api_server": f"{ROOT_PREFIX}/api",
            "pdbe_graph_server": f"{ROOT_PREFIX}/graph",
            "pdbe_search_server": f"{ROOT_PREFIX}/search",
            "pdbe_apps_server": f"{ROOT_PREFIX}/apps",
        }

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
            ) as streams:
                await server.run(
                    streams[0], streams[1], server.create_initialization_options()
                )
            return Response()

        starlette_app = Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse, methods=["GET", "POST"]),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        uvicorn.run(
            starlette_app, host="0.0.0.0", port=port, root_path=root_paths[server_type]
        )

    else:
        from mcp.server.stdio import stdio_server

        async def arun():
            async with stdio_server() as streams:
                await server.run(
                    streams[0], streams[1], server.create_initialization_options()
                )

        anyio.run(arun)

    return 0


if __name__ == "__main__":
    main()
