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
    This tool allows users to perform search queries on the PDBe database using Solr's querying capabilities. Users can specify various parameters to refine their search and retrieve relevant results.
    Expected Input Parameters:
    - query (string): The search query string to be executed.
    - filters (list of strings, optional): A list of filter queries to narrow down the search results.
    - sort (string, optional): The sorting criteria for the search results.
    - start (integer, optional): The starting index for pagination of results.
    - rows (integer, optional): The number of results to return.

    Example Input:
    {
        "query": "pdb_id:1cbs",
        "filters": ["deposition_date"],
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
                    "filters": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "sort": {"type": "string"},
                    "start": {"type": "integer"},
                    "rows": {"type": "integer"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(
                title="Run PDBe Search Query",
                destructiveHint=False,
                readOnlyHint=False,
                idempotentHint=False,
            ),
        )

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
        query = arguments.get("query", "")
        filters = arguments.get("filters", [])
        sort = arguments.get("sort", None)
        start = arguments.get("start", 0)
        rows = arguments.get("rows", 10)

        # Filter out None values from the fields dictionary
        fields = {
            "q": query,
            "start": str(start),
            "rows": str(rows),
        }
        if sort is not None:
            fields["sort"] = sort
        if filters:
            fields["fl"] = ",".join(filters)

        data = HTTPClient.get(conf.search.search_api, params=fields)

        if "response" not in data:
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
                    f"  {key}: {', '.join(str(v) for v in set(value)) if isinstance(value, list) else str(value)}"
                )

        return "\n".join(results)
