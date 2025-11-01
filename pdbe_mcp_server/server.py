from typing import Any, Callable, Sequence

import anyio
import click
import mcp.types as types
from mcp.server.lowlevel import Server
from omegaconf import DictConfig

from pdbe_mcp_server import get_config
from pdbe_mcp_server.api_tools import create_mcp_tools_from_openapi
from pdbe_mcp_server.graph_tools import GraphTools
from pdbe_mcp_server.search_tools import SearchTools

search_tools: SearchTools = SearchTools()
graph_tools: GraphTools = GraphTools()

conf: DictConfig = get_config()


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


def build_pdbe_api_server() -> Server:
    api_server = Server("pdbe-api-server")
    generator, available_tools = create_mcp_tools_from_openapi(conf.api.openapi_url)

    @api_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return available_tools

    @api_server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if arguments is None:
            arguments = {}
        return generator.call_tool(name, arguments)

    return api_server


def build_graph_server() -> Server:
    graph_server = Server("pdbe-graph-server")

    @graph_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            graph_tools.get_pdbe_graph_nodes_tool(),
            graph_tools.get_pdbe_graph_edges_tool(),
        ]

    @graph_server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if name == "pdbe_graph_nodes":
            return [types.TextContent(text=graph_tools.format_nodes(), type="text")]
        elif name == "pdbe_graph_edges":
            return [types.TextContent(text=graph_tools.format_edges(), type="text")]
        else:
            raise ValueError(f"Unknown tool name: {name}")

    return graph_server


def build_pdbe_search_server() -> Server:
    search_server = Server(
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
        if name == "get_search_schema":
            return [
                types.TextContent(type="text", text=search_tools.get_search_schema())
            ]
        elif name == "run_search_query":
            return [
                types.TextContent(
                    type="text",
                    text=search_tools.run_search_query(arguments),
                )
            ]
        else:
            raise ValueError(f"Unknown tool name: {name}")

    return search_server


factory.register("pdbe_graph_server", build_graph_server)
factory.register("pdbe_api_server", build_pdbe_api_server)
factory.register("pdbe_search_server", build_pdbe_search_server)


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
                Route("/sse", endpoint=handle_sse, methods=["GET"]),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        uvicorn.run(starlette_app, host="0.0.0.0", port=port)

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
