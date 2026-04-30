from typing import Any

import mcp.types as types
from omegaconf import DictConfig

from pdbe_mcp_server import get_config
from pdbe_mcp_server.utils import HTTPClient

conf: DictConfig = get_config()


class SearchTools:
    def get_run_search_query_tool(self) -> types.Tool:
        return types.Tool(
            name="run_search_query",
            description="""
Executes a search query against the PDBe Solr search service.
    This tool exposes common Solr query parameters directly so users can construct fielded queries, filter queries, field lists, facets, grouping, sorting, and pagination against the PDBe search index.
    IMPORTANT: `query` is passed to Solr as the raw `q` parameter. Use Solr query syntax such as `*:*`, `pdb_id:1cbs`, `text:*kinase*`, boolean clauses, ranges, and boosts as needed.
    IMPORTANT: the `text` field is a copy field that contains the full searchable text aggregated from the document. Use `text:*<term>*` when you want a broad wildcard text search.
    Expected Input Parameters:
    - query (string): Raw Solr query string passed as `q`.
    - fl (string or list of strings, optional): Solr field list. The legacy `filters` parameter is also accepted as an alias.
    - filters (list of strings, optional): Backwards-compatible alias for `fl`.
    - fq (string, object, list of strings, or list of objects, optional): Solr filter query or queries to narrow down the search results. Objects are converted to fielded filters, e.g. {"experimental_method": "X-ray diffraction"} becomes experimental_method:"X-ray diffraction".
    - sort (string, optional): The sorting criteria for the search results.
    - start (integer, optional): The starting index for pagination of results.
    - rows (integer, optional): The number of results to return.
    - facet (boolean, optional): Enable Solr faceting.
    - facet_fields (string or list of strings, optional): Field facets, sent as `facet.field`.
    - facet_queries (string or list of strings, optional): Query facets, sent as `facet.query`.
    - facet_limit, facet_mincount, facet_sort (optional): Common facet controls.
    - group (boolean, optional): Enable Solr grouping.
    - group_field (string or list of strings, optional): Grouping field, sent as `group.field`.
    - group_limit, group_offset, group_sort (optional): Common grouping controls.
    - params (object, optional): Additional Solr parameters to pass through for advanced use.

    Example Input:
    {
        "query": "text:*kinase*",
        "fl": ["pdb_id", "title", "deposition_date"],
        "fq": ["experimental_method:\"X-ray diffraction\""],
        "facet": true,
        "facet_fields": ["experimental_method"],
        "sort": "deposition_date desc",
        "start": 0,
        "rows": 10
    }

    Expected Output Format:
    A text representation of the search results, formatted in a readable manner. The output will include:
    - Metadata about the search results (e.g., number of documents found, start index).
    - A list of documents matching the search query, with each document's fields and values clearly presented.
    The output will be structured to facilitate easy interpretation of the search results, allowing users to quickly identify relevant information.
            """,
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "fl": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        ],
                    },
                    "filters": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "fq": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "additionalProperties": {
                                    "oneOf": [
                                        {"type": "string"},
                                        {"type": "number"},
                                        {"type": "integer"},
                                        {"type": "boolean"},
                                    ]
                                },
                            },
                            {
                                "type": "array",
                                "items": {
                                    "oneOf": [
                                        {"type": "string"},
                                        {
                                            "type": "object",
                                            "additionalProperties": {
                                                "oneOf": [
                                                    {"type": "string"},
                                                    {"type": "number"},
                                                    {"type": "integer"},
                                                    {"type": "boolean"},
                                                ]
                                            },
                                        },
                                    ]
                                },
                            },
                        ],
                    },
                    "sort": {"type": "string"},
                    "start": {"type": "integer"},
                    "rows": {"type": "integer"},
                    "facet": {"type": "boolean"},
                    "facet_fields": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        ],
                    },
                    "facet_queries": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        ],
                    },
                    "facet_limit": {"type": "integer"},
                    "facet_mincount": {"type": "integer"},
                    "facet_sort": {"type": "string"},
                    "group": {"type": "boolean"},
                    "group_field": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        ],
                    },
                    "group_limit": {"type": "integer"},
                    "group_offset": {"type": "integer"},
                    "group_sort": {"type": "string"},
                    "params": {
                        "type": "object",
                        "additionalProperties": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "number"},
                                {"type": "integer"},
                                {"type": "boolean"},
                                {
                                    "type": "array",
                                    "items": {
                                        "oneOf": [
                                            {"type": "string"},
                                            {"type": "number"},
                                            {"type": "integer"},
                                            {"type": "boolean"},
                                        ]
                                    },
                                },
                            ]
                        },
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(
                title="Run PDBe Search Query",
                destructiveHint=False,
                readOnlyHint=True,
                idempotentHint=True,
            ),
        )

    @staticmethod
    def _as_solr_value(value: Any) -> Any:
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, int | float):
            return str(value)
        return value

    @classmethod
    def _add_param(
        cls, params: dict[str, Any], solr_name: str, value: Any, *, join_lists: bool
    ) -> None:
        if value is None:
            return
        if isinstance(value, list):
            converted = [cls._as_solr_value(item) for item in value]
            params[solr_name] = ",".join(converted) if join_lists else converted
            return
        params[solr_name] = cls._as_solr_value(value)

    @classmethod
    def _as_solr_filter_value(cls, value: Any) -> str:
        converted = str(cls._as_solr_value(value))
        if " " in converted and not (
            converted.startswith('"') and converted.endswith('"')
        ):
            return f'"{converted}"'
        return converted

    @classmethod
    def _normalize_filter_queries(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return [
                f"{field}:{cls._as_solr_filter_value(field_value)}"
                for field, field_value in value.items()
            ]
        if isinstance(value, list):
            normalized: list[Any] = []
            for item in value:
                item_value = cls._normalize_filter_queries(item)
                if isinstance(item_value, list):
                    normalized.extend(item_value)
                elif item_value is not None:
                    normalized.append(item_value)
            return normalized
        return cls._as_solr_value(value)

    @staticmethod
    def _format_value(value: Any, indent: int = 0) -> list[str]:
        prefix = " " * indent
        if isinstance(value, dict):
            lines: list[str] = []
            for key, nested_value in value.items():
                if isinstance(nested_value, dict | list):
                    lines.append(f"{prefix}{key}:")
                    lines.extend(SearchTools._format_value(nested_value, indent + 2))
                else:
                    lines.append(f"{prefix}{key}: {nested_value}")
            return lines
        if isinstance(value, list):
            if not value:
                return [f"{prefix}[]"]
            if all(not isinstance(item, dict | list) for item in value):
                return [f"{prefix}{', '.join(str(item) for item in value)}"]
            lines = []
            for item in value:
                lines.extend(SearchTools._format_value(item, indent))
            return lines
        return [f"{prefix}{value}"]

    @classmethod
    def _build_solr_params(cls, arguments: dict[str, Any]) -> dict[str, Any]:
        params = arguments.get("params", {}).copy()
        fields = arguments.get("fl", arguments.get("filters"))

        cls._add_param(params, "q", arguments.get("query"), join_lists=False)
        cls._add_param(params, "start", arguments.get("start", 0), join_lists=False)
        cls._add_param(params, "rows", arguments.get("rows", 10), join_lists=False)
        cls._add_param(params, "sort", arguments.get("sort"), join_lists=False)
        cls._add_param(params, "fl", fields, join_lists=True)
        cls._add_param(
            params,
            "fq",
            cls._normalize_filter_queries(arguments.get("fq")),
            join_lists=False,
        )
        cls._add_param(params, "facet", arguments.get("facet"), join_lists=False)
        cls._add_param(
            params, "facet.field", arguments.get("facet_fields"), join_lists=False
        )
        cls._add_param(
            params, "facet.query", arguments.get("facet_queries"), join_lists=False
        )
        cls._add_param(
            params, "facet.limit", arguments.get("facet_limit"), join_lists=False
        )
        cls._add_param(
            params,
            "facet.mincount",
            arguments.get("facet_mincount"),
            join_lists=False,
        )
        cls._add_param(
            params, "facet.sort", arguments.get("facet_sort"), join_lists=False
        )
        cls._add_param(params, "group", arguments.get("group"), join_lists=False)
        cls._add_param(
            params, "group.field", arguments.get("group_field"), join_lists=False
        )
        cls._add_param(
            params, "group.limit", arguments.get("group_limit"), join_lists=False
        )
        cls._add_param(
            params, "group.offset", arguments.get("group_offset"), join_lists=False
        )
        cls._add_param(
            params, "group.sort", arguments.get("group_sort"), join_lists=False
        )
        return params

    def get_search_schema_tool(self) -> types.Tool:
        return types.Tool(
            name="get_search_schema",
            description="""
Retrieves the Solr search schema for the PDBe search service. You can use this tool to understand the structure and fields available in the PDBe search index. Once you have the schema, you can use it to construct more effective search queries and run the query using the `run_search_query` tool.
    This tool returns a detailed schema of the Solr search index used by PDBe. The schema includes information about all the fields available for searching, along with their types, whether they are stored or indexed, and any relevant descriptions.
    Expected Output Format:
    A text representation of the search schema, formatted as a table with the following columns:
    - Field Name: The name of the field in the Solr schema.
    - Type: The data type of the field (e.g., string, integer, date).
    - Stored: Indicates whether the field is stored in the index (true/false).
    - Indexed: Indicates whether the field is indexed for searching (true/false).
    - Description: A brief description of the field and its purpose.
    The output will be structured in a way that is easy to read and understand, allowing users to quickly grasp the available search fields and their characteristics.
            """,
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(
                title="Get PDBe Search Schema",
                destructiveHint=False,
                readOnlyHint=True,
                idempotentHint=True,
            ),
        )

    def get_search_schema(self) -> str:
        schema = HTTPClient.get(conf.search.schema_url)
        content = ["Field Name;Type;Stored;Indexed;Description"]
        for field, values in schema.get("fields", {}).items():
            content.append(
                f"{field}; {values.get('type')}; {values.get('stored')}; {values.get('indexed')}; {values.get('description')}"
            )

        return "\n".join(content)

    def run_search_query(self, arguments: dict[str, Any]) -> str:
        fields = self._build_solr_params(arguments)
        data = HTTPClient.get(conf.search.search_api, params=fields)

        if data is None or "response" not in data:
            raise Exception("Invalid response from search service")
        # Extract the relevant information from the response
        response = data["response"]
        docs = response.get("docs", [])
        num_found = response.get("numFound", 0)
        results = [
            "Results metadata:",
            f"Number of documents found: {num_found}",
            f"Start index: {response.get('start', 0)}",
            "Documents:",
        ]
        for i, doc in enumerate(docs, start=1):
            results.append(f"Document {i}:")
            for key, value in doc.items():
                results.append(
                    f"  {key}: {', '.join(str(v) for v in value) if isinstance(value, list) else str(value)}"
                )

        if "facet_counts" in data:
            results.append("Facet counts:")
            results.extend(self._format_value(data["facet_counts"], indent=2))

        if "grouped" in data:
            results.append("Grouped results:")
            results.extend(self._format_value(data["grouped"], indent=2))

        return "\n".join(results)
