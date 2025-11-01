"""Tests for api_tools module."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from pdbe_mcp_server.api_tools import (
    OpenAPIToMCPGenerator,
    create_mcp_tools_from_openapi,
)


class TestOpenAPIToMCPGenerator:
    """Tests for OpenAPIToMCPGenerator class."""

    def test_initialization(self) -> None:
        """Test generator initialization."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        assert generator.openapi_url == "https://example.com/openapi.json"
        assert generator.openapi_spec == {}
        assert generator.tools == []

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_load_openapi_spec_success(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test successful loading of OpenAPI spec."""
        mock_get.return_value = mock_openapi_spec

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        spec = generator.load_openapi_spec()

        assert spec == mock_openapi_spec
        assert generator.openapi_spec == mock_openapi_spec
        mock_get.assert_called_once_with("https://example.com/openapi.json")

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_load_openapi_spec_failure(self, mock_get: MagicMock) -> None:
        """Test failed loading of OpenAPI spec."""
        mock_get.side_effect = requests.HTTPError("Not Found")

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        with pytest.raises(Exception, match="Failed to load OpenAPI spec"):
            generator.load_openapi_spec()

    def test_convert_openapi_type_to_json_schema(self) -> None:
        """Test OpenAPI to JSON Schema type conversion."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        # Test simple type
        param_schema = {"type": "string", "description": "A string parameter"}
        result = generator._convert_openapi_type_to_json_schema(param_schema)

        assert result["type"] == "string"
        assert result["description"] == "A string parameter"

    def test_convert_openapi_type_with_enum(self) -> None:
        """Test conversion with enum values."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        param_schema = {
            "type": "string",
            "enum": ["json", "xml"],
            "default": "json",
        }
        result = generator._convert_openapi_type_to_json_schema(param_schema)

        assert result["enum"] == ["json", "xml"]
        assert result["default"] == "json"

    def test_convert_openapi_type_array(self) -> None:
        """Test conversion of array type."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        param_schema = {"type": "array", "items": {"type": "string"}}
        result = generator._convert_openapi_type_to_json_schema(param_schema)

        assert result["type"] == "array"
        assert result["items"]["type"] == "string"

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_list_tools(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test generating MCP tools from OpenAPI spec."""
        mock_get.return_value = mock_openapi_spec

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        tools = generator.list_tools()

        # Should create one tool from the enabled endpoint
        assert len(tools) == 1
        assert tools[0].name == "get_test"
        assert tools[0].description is not None
        assert "test data" in tools[0].description.lower()

        # Check input schema
        assert "id" in tools[0].inputSchema["properties"]
        assert "format" in tools[0].inputSchema["properties"]
        assert "id" in tools[0].inputSchema["required"]

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_list_tools_skips_disabled(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test that disabled endpoints are skipped."""
        mock_get.return_value = mock_openapi_spec

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        tools = generator.list_tools()

        # Should not include the disabled endpoint
        tool_names = [tool.name for tool in tools]
        assert "disabled_endpoint" not in tool_names

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_list_tools_stores_metadata(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test that tool metadata is stored."""
        mock_get.return_value = mock_openapi_spec

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.list_tools()

        assert len(generator.tools) == 1
        tool_meta = generator.tools[0]
        assert tool_meta["name"] == "get_test"
        assert tool_meta["method"] == "GET"
        assert tool_meta["path"] == "/test/{id}"
        assert "id" in tool_meta["path_params"]
        assert "format" in tool_meta["query_params"]

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_call_tool_success(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test successful tool call."""
        # First call loads spec, second call executes the tool
        mock_get.side_effect = [
            mock_openapi_spec,
            {"result": "success", "data": "test_data"},
        ]

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.list_tools()

        arguments = {"id": "test123", "format": "json"}
        result = generator.call_tool("get_test", arguments)

        assert len(result) == 1
        assert result[0].type == "text"
        assert "success" in result[0].text
        assert "test_data" in result[0].text

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_call_tool_unknown_tool(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test calling unknown tool."""
        mock_get.return_value = mock_openapi_spec

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.list_tools()

        with pytest.raises(ValueError, match="Unknown tool"):
            generator.call_tool("nonexistent_tool", {})

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_call_tool_missing_required_param(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test calling tool with missing required parameter."""
        mock_get.return_value = mock_openapi_spec

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.list_tools()

        with pytest.raises(ValueError, match="Missing required path parameter"):
            generator.call_tool("get_test", {})

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_call_tool_request_exception(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test handling of request exceptions."""
        # First call loads spec, second raises exception
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        error = requests.RequestException("Server Error")
        error.response = mock_response

        mock_get.side_effect = [mock_openapi_spec, error]

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.list_tools()

        arguments = {"id": "test123"}
        result = generator.call_tool("get_test", arguments)

        assert len(result) == 1
        from mcp.types import TextContent

        assert isinstance(result[0], TextContent)
        assert "API request failed" in result[0].text
        assert "500" in result[0].text

    def test_extract_parameters(self) -> None:
        """Test parameter extraction."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        path_params = [
            {
                "name": "id",
                "in": "path",
                "required": True,
                "schema": {"type": "string", "description": "ID parameter"},
            }
        ]

        query_params = [
            {
                "name": "limit",
                "in": "query",
                "required": False,
                "schema": {"type": "integer"},
                "description": "Result limit",
            }
        ]

        properties, required = generator._extract_parameters(path_params, query_params)

        assert "id" in properties
        assert "limit" in properties
        assert properties["limit"]["description"] == "Result limit"
        assert "id" in required
        assert "limit" not in required


class TestCreateMCPToolsFromOpenAPI:
    """Tests for create_mcp_tools_from_openapi function."""

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_create_mcp_tools_from_openapi(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test creating MCP tools from OpenAPI URL."""
        mock_get.return_value = mock_openapi_spec

        generator, tools = create_mcp_tools_from_openapi(
            "https://example.com/openapi.json"
        )

        assert isinstance(generator, OpenAPIToMCPGenerator)
        assert len(tools) == 1
        assert tools[0].name == "get_test"
