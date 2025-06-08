from typing import Any, Callable, Dict, List

import anyio
import click
import mcp.types as types
from mcp.server.lowlevel import Server

from pdbe_mcp_server.api_tools import create_mcp_tools_from_openapi


class MCPServerFactory:
    """
    Factory class to create an MCP server instance.
    """

    def __init__(self) -> None:
        self._builders: Dict[str, Callable[[], Any]] = {}

    def register(self, name: str, builder_func: Callable[[], Any]) -> None:
        self._builders[name] = builder_func

    def create(self, name: str) -> Any:
        if name not in self._builders:
            raise ValueError(f"No builder registered for {name}")
        return self._builders[name]()

    def available_types(self) -> List[str]:
        return list(self._builders.keys())


# Global factory instance
factory = MCPServerFactory()


def build_pdbe_api_server() -> Server:
    api_server = Server("pdbe-api-server")
    openapi_url = "https://www.ebi.ac.uk/pdbe/api/v2/openapi.json"
    generator, available_tools = create_mcp_tools_from_openapi(openapi_url)

    @api_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return available_tools

    @api_server.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> List[
        types.TextContent
        | types.ImageContent
        | types.EmbeddedResource
        | types.CallToolResult
    ]:
        try:
            if arguments is None:
                arguments = {}
            return generator.call_tool(name, arguments)
        except Exception as error:
            return [
                types.CallToolResult(
                    isError=True,
                    content=[
                        types.TextContent(type="text", text=f"Error: {str(error)}")
                    ],
                )
            ]

    return api_server


def build_graph_server() -> Server:
    graph_server = Server("pdbe-graph-server")

    @graph_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="pdbe_graph_nodes",
                description="""
Retrieves metadata about all node types (also known as "labels") defined in the PDBe (PDBe-KB) graph database schema.

This tool returns detailed information about each node label in the graph database. For every node label, it includes:
- The label name (e.g., 'Person', 'Product')
- A human-readable description of the node type
- A list of parameters (i.e., properties/attributes) associated with this node
- For each parameter:
  - The name of the property
  - A brief description of the property

Expected Output Format:
[
  {
    "label": "Person",
    "description": "Represents an individual in the network",
    "parameters": [
      {
        "name": "name",
        "description": "The full name of the person"
      },
      {
        "name": "birthdate",
        "description": "The date of birth of the person"
      }
    ]
  },
  ...
]
""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                annotations=types.ToolAnnotations(
                    title="Get PDBe Graph Nodes",
                    destructiveHint=False,
                    readOnlyHint=True,
                    idempotentHint=True,
                ),
            ),
            types.Tool(
                name="pdbe_graph_edges",
                description="""
Retrieves metadata about all relationship types (edges) defined in the PDBe (PDBe-KB) graph database schema.

This tool returns detailed information about each relationship (edge) in the graph. For every relationship type, it includes:
- The relationship label (e.g., 'FRIEND_OF', 'PURCHASED')
- A human-readable description of the relationship
- The 'from' node label and 'to' node label, defining the direction and connectivity
- A list of properties associated with the relationship
- For each property:
  - The name of the property
  - A brief description of the property

Expected Output Format:
[
  {
    "label": "FRIEND_OF",
    "description": "Indicates a friendship between two people",
    "from": "Person",
    "to": "Person",
    "properties": [
      {
        "name": "since",
        "description": "The date when the friendship started"
      }
    ]
  },
  ...
]
""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                annotations=types.ToolAnnotations(
                    title="Get PDBe Graph Edges",
                    destructiveHint=False,
                    readOnlyHint=True,
                    idempotentHint=True,
                ),
            ),
        ]

    @graph_server.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> List[
        types.TextContent
        | types.ImageContent
        | types.EmbeddedResource
        | types.CallToolResult
    ]:
        from pdbe_mcp_server.graph_tools import GraphTools

        graph_tools = GraphTools()

        try:
            if name == "pdbe_graph_nodes":
                return [types.TextContent(text=graph_tools.format_nodes(), type="text")]
            elif name == "pdbe_graph_edges":
                return [types.TextContent(text=graph_tools.format_edges(), type="text")]
            else:
                raise Exception(f"Unknown tool name: {name}")
        except Exception as error:
            return [
                types.CallToolResult(
                    isError=True,
                    content=[
                        types.TextContent(type="text", text=f"Error: {str(error)}")
                    ],
                )
            ]

    return graph_server


factory.register("pdbe_graph_server", build_graph_server)
factory.register("pdbe_api_server", build_pdbe_api_server)


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
