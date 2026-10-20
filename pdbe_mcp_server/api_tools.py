import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from urllib.parse import quote, urljoin

import mcp.types as types
import requests
from omegaconf import DictConfig

from pdbe_mcp_server import get_config
from pdbe_mcp_server.execution import ToolDeadlineExceeded
from pdbe_mcp_server.utils import HTTPClient

logger = logging.getLogger(__name__)

conf: DictConfig = get_config()


def _toon_enabled() -> bool:
    return os.getenv("TOON_ENABLED", "false").lower() == "true"


class OpenAPIToMCPGenerator:
    def __init__(self, openapi_url: str) -> None:
        """
        Initialize the generator with an OpenAPI JSON URL.

        Args:
            openapi_url: URL to the OpenAPI JSON specification
        """
        self.openapi_url: str = openapi_url
        self.openapi_spec: dict[str, Any] = {}
        self.base_url: str = str(conf.api.base_url)
        self.tools: list[dict[str, Any]] = []
        self.operations: dict[tuple[str, str], dict[str, Any]] = {}

    def index_operations(self) -> None:
        """Index schema GET operations independently of model tool visibility."""
        if not self.openapi_spec:
            self.load_openapi_spec()
        self.operations.clear()
        for path, item in self.openapi_spec.get("paths", {}).items():
            operation = item.get("get")
            if not isinstance(operation, dict):
                continue
            parameters = {
                (p.get("in"), p.get("name")): p
                for p in [*item.get("parameters", []), *operation.get("parameters", [])]
                if isinstance(p, dict) and "name" in p
            }
            self.operations[("GET", path)] = {
                "method": "GET",
                "path": path,
                "path_params": [
                    p["name"] for p in parameters.values() if p.get("in") == "path"
                ],
                "query_params": [
                    p["name"] for p in parameters.values() if p.get("in") == "query"
                ],
            }

    def execute_operation(
        self, method: str, path: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Return raw JSON and provenance for a registered read-only operation."""
        if not self.operations:
            self.index_operations()
        operation = self.operations.get((method.upper(), path))
        if operation is None:
            raise ValueError(f"Unknown read-only OpenAPI operation: {method} {path}")
        return self._execute_request(operation, arguments)

    def execute_api_tool(self, path: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a generated GET tool as raw data, preserving API provenance.

        Resolve by schema path so shortened tool names are not coupled to apps.
        Operations without enableMCP must use execute_operation explicitly.
        """
        if not self.tools:
            self.list_tools()
        tool = next(
            (
                item
                for item in self.tools
                if item["method"] == "GET" and item["path"] == path
            ),
            None,
        )
        if tool is None:
            raise ValueError(f"No generated API tool for GET {path}")
        return self._execute_request(tool, arguments)

    def _execute_request(
        self, operation: dict[str, Any], arguments: dict[str, Any]
    ) -> dict[str, Any]:
        path = operation["path"]
        for name in operation["path_params"]:
            if name not in arguments:
                raise ValueError(f"Missing required path parameter: {name}")
            path = path.replace(f"{{{name}}}", quote(str(arguments[name]), safe=""))
        url = urljoin(self.base_url, path.lstrip("/"))
        params = {
            name: arguments[name]
            for name in operation["query_params"]
            if name in arguments
        }
        # HTTPClient owns the retry policy and inherits the tool's deadline.
        if operation["method"] == "GET":
            data = HTTPClient.get(url, params=params or None)
        elif operation["method"] == "POST":
            data = HTTPClient.post(url)
        else:
            raise ValueError(f"Unsupported method: {operation['method']}")
        return {
            "data": data,
            "source": url,
            "parameters": params,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

    def load_openapi_spec(self) -> dict[str, Any]:
        """
        Load the OpenAPI specification from the remote URL.

        Returns:
            The parsed OpenAPI specification as a dictionary
        """
        try:
            spec = HTTPClient.get(self.openapi_url)
            self.openapi_spec = spec
            return spec

        except requests.HTTPError as e:
            raise Exception(
                f"Failed to load OpenAPI spec from {self.openapi_url}: {e}"
            ) from e

    def _convert_openapi_type_to_json_schema(
        self, param_schema: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Convert OpenAPI parameter schema to JSON Schema format.

        Args:
            param_schema: OpenAPI parameter schema

        Returns:
            JSON Schema compatible dictionary
        """
        json_schema = {}

        # Map OpenAPI types to JSON Schema types
        if "type" in param_schema:
            json_schema["type"] = param_schema["type"]

        if "description" in param_schema:
            json_schema["description"] = param_schema["description"]

        if "enum" in param_schema:
            json_schema["enum"] = param_schema["enum"]

        if "default" in param_schema:
            json_schema["default"] = param_schema["default"]

        if "format" in param_schema:
            json_schema["format"] = param_schema["format"]

        # Handle array types
        if param_schema.get("type") == "array" and "items" in param_schema:
            json_schema["items"] = self._convert_openapi_type_to_json_schema(
                param_schema["items"]
            )

        return json_schema

    def _extract_parameters(
        self, path_params: list[dict[str, Any]], query_params: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Extract and convert parameters to JSON Schema format.

        Args:
            path_params: List of path parameters
            query_params: List of query parameters

        Returns:
            JSON Schema properties and required fields
        """
        properties = {}
        required = []

        # Process path parameters
        for param in path_params:
            param_name = param["name"]
            properties[param_name] = self._convert_openapi_type_to_json_schema(
                param.get("schema", {})
            )
            schema = param.get("schema", {})
            description = schema.get("description", "")
            for key in schema:
                description += f"\n{key}: {schema[key]}"

            properties[param_name]["description"] = description
            if param.get("required", False):
                required.append(param_name)

        # Process query parameters
        for param in query_params:
            param_name = param["name"]
            properties[param_name] = self._convert_openapi_type_to_json_schema(
                param.get("schema", {})
            )
            if param.get("description"):
                properties[param_name]["description"] = param["description"]
            if param.get("required", False):
                required.append(param_name)

        return properties, required

    def _shorten_tool_name(self, tool_name: str, max_length: int = 50) -> str:
        """Intelligently shorten tool name by removing common words and abbreviating.

        Args:
            tool_name: Original tool name
            max_length: Maximum allowed length for the shortened name

        Returns:
            Shortened tool name with hash suffix for uniqueness
        """
        # Domain-specific abbreviations for PDBe
        abbreviations = {
            "get": "",
            "api": "",
            "pdb": "",
            "entry": "ent",
            "sequence": "seq",
            "validation": "val",
            "coordinates": "coord",
            "information": "info",
            "molecule": "mol",
            "structure": "struct",
            "experimental": "exp",
            "secondary": "sec",
            "annotations": "annot",
            "interface": "iface",
            "residues": "res",
            "binding": "bind",
            "sites": "sites",
            "uniprot": "unip",
            "accession": "acc",
            "compound": "comp",
            "interaction": "intx",
            "protein": "prot",
            "generic": "gen",
            "summary": "sum",
            "mapping": "map",
            "mappings": "maps",
            "domain": "dom",
            "domains": "doms",
            "statistics": "stats",
            "best": "best",
            "observed": "obs",
            "chains": "chains",
            "variation": "var",
        }

        # Split into words
        words = tool_name.split("_")

        # Apply abbreviations and filter out empty strings
        shortened = []
        for word in words:
            abbreviated = abbreviations.get(word, word)
            if abbreviated:  # Only keep non-empty strings
                shortened.append(abbreviated)

        result = "_".join(shortened)

        # If still too long, truncate intelligently while preserving most meaningful parts
        if len(result) > max_length - 9:  # Leave room for hash
            parts = result.split("_")
            if len(parts) > 3:
                # Keep first, middle indicator, and last parts
                middle = "".join(p[0] for p in parts[1:-1] if p)
                result = f"{parts[0]}_{middle}_{parts[-1]}"
            result = result[: max_length - 9]

        # Generate hash from original name for uniqueness
        hash_suffix = hashlib.md5(tool_name.encode()).hexdigest()[:8]

        # Combine shortened name with hash
        final_name = f"{result}_{hash_suffix}"

        return final_name.rstrip("_")

    def list_tools(self) -> list[types.Tool]:
        """
        Generate MCP tools from the OpenAPI specification.

        Returns:
            List of MCP Tool objects
        """
        if not self.openapi_spec:
            self.load_openapi_spec()

        self.index_operations()
        self.tools.clear()
        tools = []
        paths = self.openapi_spec.get("paths", {})

        for path, path_item in paths.items():
            for method, operation in path_item.items():
                # Skip POST methods and non-HTTP methods
                if method.lower() != "get" or not isinstance(operation, dict):
                    continue

                # skip APIs which are not enabled for MCP
                if not operation.get("enableMCP") or not operation["enableMCP"]:
                    continue

                # Generate tool name from operationId or path/method
                if "operationId" in operation:
                    tool_name = operation["operationId"]
                else:
                    # Create tool name from path and method
                    clean_path = (
                        path.replace("/", "_")
                        .replace("{", "")
                        .replace("}", "")
                        .strip("_")
                    )
                    tool_name = f"{method}_{clean_path}".replace("__", "_")

                # Shorten tool name intelligently with hash for uniqueness
                tool_name = self._shorten_tool_name(tool_name, max_length=50)

                # Get description
                description = operation.get("description", operation.get("summary"))

                # Extract parameters
                parameters = operation.get("parameters", [])
                path_params = [p for p in parameters if p.get("in") == "path"]
                query_params = [p for p in parameters if p.get("in") == "query"]

                properties, required = self._extract_parameters(
                    path_params, query_params
                )

                # Create input schema
                input_schema = {
                    "type": "object",
                    "properties": properties,
                    "additionalProperties": False,
                }

                if required:
                    input_schema["required"] = required

                # Create tool
                tool = types.Tool(
                    name=tool_name,
                    description=description,
                    inputSchema=input_schema,
                    annotations=types.ToolAnnotations(
                        title=description,
                        destructiveHint=False,
                        readOnlyHint=True,
                        idempotentHint=False,
                    ),
                )
                tools.append(tool)

                # Store tool metadata for call_tool function
                self.tools.append(
                    {
                        "name": tool_name,
                        "method": method.upper(),
                        "path": path,
                        "path_params": [p["name"] for p in path_params],
                        "query_params": [p["name"] for p in query_params],
                    }
                )

        return tools

    def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """
        Execute a tool call by making the appropriate API request.

        Args:
            name: Tool name to execute
            arguments: Arguments for the tool

        Returns:
            List of TextContent with the API response
        """
        # Find the tool metadata
        tool_info = None
        for tool in self.tools:
            if tool["name"] == name:
                tool_info = tool
                break

        if not tool_info:
            raise ValueError(f"Unknown tool: {name}")

        try:
            data = self._execute_request(tool_info, arguments)["data"]
        except ToolDeadlineExceeded:
            raise
        except requests.RequestException as error:
            error_message = f"API request failed: {error}"
            if error.response is not None:
                error_message += f"\nStatus Code: {error.response.status_code}"
                error_message += f"\nResponse: {error.response.text}"
            return [types.TextContent(type="text", text=error_message)]

        if _toon_enabled():
            try:
                import toon

                result_text = toon.encode(data)
                if not isinstance(result_text, str):
                    result_text = str(result_text)
            except Exception as e:
                logger.warning("TOON encoding failed, falling back to JSON: %s", e)
                result_text = "TOON failed; JSON fallback:\n" + json.dumps(
                    data, indent=2
                )
        else:
            result_text = json.dumps(data, indent=2)
        return [types.TextContent(type="text", text=result_text)]


def create_mcp_tools_from_openapi(
    openapi_url: str,
) -> tuple[OpenAPIToMCPGenerator, list[types.Tool]]:
    """
    Main function to create MCP tools from an OpenAPI specification.

    Args:
        openapi_url: URL to the OpenAPI JSON specification

    Returns:
        Tuple of (generator_instance, list_of_tools)
    """
    generator = OpenAPIToMCPGenerator(openapi_url)
    tools = generator.list_tools()
    return generator, tools


@lru_cache(maxsize=1)
def get_shared_api_generator() -> OpenAPIToMCPGenerator:
    """One schema and operation registry per server process."""
    generator, _ = create_mcp_tools_from_openapi(str(conf.api.openapi_url))
    return generator
