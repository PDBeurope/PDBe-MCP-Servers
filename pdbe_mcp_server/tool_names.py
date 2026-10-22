"""Public tool names and backwards-compatible dispatch for all PDBe servers."""

from functools import wraps
from typing import Awaitable, Callable, cast

import mcp.types as types
from mcp.server.lowlevel import Server

from pdbe_mcp_server.skills import SkillCatalog, run_with_skills

TOOL_NAMESPACE = "ebi-pdbe-"
_ListToolsCallback = (
    Callable[[], Awaitable[list[types.Tool]]]
    | Callable[[types.ListToolsRequest], Awaitable[types.ListToolsResult]]
)
_CURATED_NAMES = {
    "pdbe_update_workspace": "update_workspace",
    "pdbe_open_structure": "open_structure",
    "pdbe_compare_structures": "compare_structures",
    "pdbe_build_mvs": "build_mvs",
    "pdbe_build_mvs_story": "build_mvs_story",
    "pdbe_get_ai_summary": "get_ai_summary",
    "get_pdbe_search_schema": "search_schema",
    "run_pdbe_search_query": "search",
    "pdbe_graph_nodes": "graph_nodes",
    "pdbe_graph_edges": "graph_edges",
    "pdbe_graph_node_relationships": "graph_node_relationships",
    "pdbe_graph_example_queries": "graph_example_queries",
    "pdbe_graph_indexes": "graph_indexes",
    "pdbe_run_cypher_query": "run_cypher_query",
}


def public_tool_name(name: str) -> str:
    """Prefix generated names and give curated tools stable, concise suffixes."""
    if name.startswith(TOOL_NAMESPACE):
        return name
    return TOOL_NAMESPACE + _CURATED_NAMES.get(name, name)


class PDBeServer(Server):
    """Advertise canonical names while accepting legacy calls before validation.

    The SDK's own decorators still perform input/output validation and result
    normalization. Translating the request first prevents old aliases from
    bypassing validation because they are absent from tools/list.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._internal_tool_names: dict[str, str] = {}
        self.skill_catalog: SkillCatalog | None = None
        self.tool_input_normalizers: dict[str, Callable] = {}

    async def run(
        self,
        read_stream,
        write_stream,
        initialization_options,
        raise_exceptions=False,
        stateless=False,
    ):
        if self.skill_catalog is None:
            return await super().run(
                read_stream,
                write_stream,
                initialization_options,
                raise_exceptions=raise_exceptions,
                stateless=stateless,
            )
        return await run_with_skills(
            self.skill_catalog,
            self.name,
            super().run,
            read_stream,
            write_stream,
            initialization_options,
            raise_exceptions=raise_exceptions,
            stateless=stateless,
        )

    def list_tools(self):
        decorate = super().list_tools()

        def register(func):
            @wraps(func)
            async def namespaced(*args, **kwargs):
                result = await func(*args, **kwargs)
                tools = (
                    result.tools
                    if isinstance(result, types.ListToolsResult)
                    else result
                )
                internal_names = {}
                public_tools = []
                for tool in tools:
                    name = public_tool_name(tool.name)
                    if name in internal_names:
                        raise ValueError(f"Duplicate public tool name: {name}")
                    internal_names[name] = tool.name
                    # Preserve annotations, output schemas and all UI metadata.
                    public_tools.append(tool.model_copy(update={"name": name}))
                if isinstance(result, types.ListToolsResult):
                    self._internal_tool_names.update(internal_names)
                    return result.model_copy(update={"tools": public_tools})
                self._internal_tool_names = internal_names
                return public_tools

            # wraps preserves the callback's original signature; the two SDK
            # list-tools signatures return different result types.
            decorate(cast(_ListToolsCallback, namespaced))
            return func

        return register

    def call_tool(self, *, validate_input: bool = True):
        decorate = super().call_tool(validate_input=validate_input)

        def register(func):
            @wraps(func)
            async def dispatch(name, arguments):
                return await func(self._internal_tool_names.get(name, name), arguments)

            decorate(dispatch)
            handler = self.request_handlers[types.CallToolRequest]

            async def accept_alias(request: types.CallToolRequest):
                canonical = public_tool_name(request.params.name)
                arguments = request.params.arguments or {}
                normalizer = self.tool_input_normalizers.get(canonical)
                if normalizer is not None:
                    normalized = normalizer(arguments)
                    if isinstance(normalized, types.CallToolResult):
                        return types.ServerResult(normalized)
                    arguments = normalized
                # Copy rather than mutate requests forwarded through /all.
                request = request.model_copy(
                    update={
                        "params": request.params.model_copy(
                            update={"name": canonical, "arguments": arguments}
                        )
                    }
                )
                return await handler(request)

            self.request_handlers[types.CallToolRequest] = accept_alias
            return func

        return register
