import json
from typing import Any
from urllib.parse import urljoin

import mcp.types as types
import requests
from omegaconf import DictConfig

from pdbe_mcp_server import get_config
from pdbe_mcp_server.utils import HTTPClient

conf: DictConfig = get_config()


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

    def list_tools(self) -> list[types.Tool]:
        """
        Generate MCP tools from the OpenAPI specification.

        Returns:
            List of MCP Tool objects
        """
        if not self.openapi_spec:
            self.load_openapi_spec()

        tools = []
        paths = self.openapi_spec.get("paths", {})

        for path, path_item in paths.items():
            for method, operation in path_item.items():
                # Skip POST methods and non-HTTP methods
                if method.upper() == "POST" or method.startswith("x-"):
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

                # trim tool name to at most 60 characters
                tool_name = tool_name[:60]

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

        # Build the URL
        url_path = tool_info["path"]

        # Replace path parameters
        for param_name in tool_info["path_params"]:
            if param_name not in arguments:
                raise ValueError(f"Missing required path parameter: {param_name}")
            url_path = url_path.replace(f"{{{param_name}}}", str(arguments[param_name]))

        # Build full URL
        full_url = urljoin(self.base_url, url_path.lstrip("/"))

        # Build path parameters
        path_params = {}
        for param_name in tool_info["path_params"]:
            if param_name in arguments:
                path_params[param_name] = arguments[param_name]

        try:
            if tool_info["method"] == "GET":
                data = HTTPClient.get(full_url)
            elif tool_info["method"] == "POST":
                data = HTTPClient.post(full_url)
            else:
                # unsupported method, raise an error
                raise ValueError(f"Unsupported method: {tool_info['method']}")

            result_text = json.dumps(data, indent=2)
            return [types.TextContent(type="text", text=result_text)]

        except requests.RequestException as e:
            error_message = f"API request failed: {e}"
            if hasattr(e, "response") and e.response is not None:
                error_message += f"\nStatus Code: {e.response.status_code}"
                error_message += f"\nResponse: {e.response.text}"

            return [types.TextContent(type="text", text=error_message)]


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
