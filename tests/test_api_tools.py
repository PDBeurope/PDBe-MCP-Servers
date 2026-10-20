"""Tests for api_tools module."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from pdbe_mcp_server.api_tools import (
    OpenAPIToMCPGenerator,
    create_mcp_tools_from_openapi,
)


def get_expected_shortened_name(original_name: str) -> str:
    """Helper to compute expected shortened tool name."""
    generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
    return generator._shorten_tool_name(original_name)


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
        # Tool name should be shortened and hashed
        expected_name = get_expected_shortened_name("get_test")
        assert tools[0].name == expected_name
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
        disabled_name = get_expected_shortened_name("disabled_endpoint")
        assert disabled_name not in tool_names

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
        # Tool name should be shortened and hashed
        expected_name = get_expected_shortened_name("get_test")
        assert tool_meta["name"] == expected_name
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
        tool_name = get_expected_shortened_name("get_test")
        result = generator.call_tool(tool_name, arguments)

        assert len(result) == 1
        assert result[0].type == "text"
        assert "success" in result[0].text
        assert "test_data" in result[0].text

        mock_get.assert_called_with(
            "https://www.ebi.ac.uk/pdbe/api/v2/test/test123",
            params={"format": "json"},
        )

    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_call_tool_omits_absent_query_params(
        self, mock_get: MagicMock, mock_openapi_spec: dict[str, Any]
    ) -> None:
        """Test that missing optional query parameters are not sent."""
        mock_get.side_effect = [
            mock_openapi_spec,
            {"result": "success", "data": "test_data"},
        ]

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.list_tools()

        tool_name = get_expected_shortened_name("get_test")
        result = generator.call_tool(tool_name, {"id": "test123"})

        assert len(result) == 1
        assert result[0].type == "text"
        assert "success" in result[0].text
        mock_get.assert_called_with(
            "https://www.ebi.ac.uk/pdbe/api/v2/test/test123",
            params=None,
        )

    @patch("toon.encode")
    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_call_tool_toon_success(
        self,
        mock_get: MagicMock,
        mock_encode: MagicMock,
        mock_openapi_spec: dict[str, Any],
    ) -> None:
        """Test TOON encoding success path."""
        mock_get.side_effect = [mock_openapi_spec, {"result": "success"}]
        mock_encode.return_value = "TOON_DATA"

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.list_tools()

        tool_name = get_expected_shortened_name("get_test")
        with patch.dict("os.environ", {"TOON_ENABLED": "true"}):
            result = generator.call_tool(tool_name, {"id": "test123"})

        assert len(result) == 1
        assert result[0].type == "text"
        assert result[0].text == "TOON_DATA"
        mock_encode.assert_called_once()

    @patch("toon.encode")
    @patch("pdbe_mcp_server.api_tools.HTTPClient.get")
    def test_call_tool_toon_fallback_to_json(
        self,
        mock_get: MagicMock,
        mock_encode: MagicMock,
        mock_openapi_spec: dict[str, Any],
    ) -> None:
        """Test TOON encoding failure falls back to JSON."""
        mock_get.side_effect = [mock_openapi_spec, {"result": "success"}]
        mock_encode.side_effect = Exception("TOON failed")

        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.list_tools()

        tool_name = get_expected_shortened_name("get_test")
        with patch.dict("os.environ", {"TOON_ENABLED": "true"}):
            result = generator.call_tool(tool_name, {"id": "test123"})

        assert len(result) == 1
        assert result[0].type == "text"
        assert "TOON failed; JSON fallback" in result[0].text
        assert '"result": "success"' in result[0].text
        mock_encode.assert_called_once()

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

        tool_name = get_expected_shortened_name("get_test")
        with pytest.raises(ValueError, match="Missing required path parameter"):
            generator.call_tool(tool_name, {})

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
        tool_name = get_expected_shortened_name("get_test")
        result = generator.call_tool(tool_name, arguments)

        assert len(result) == 1
        from mcp.types import TextContent

        assert isinstance(result[0], TextContent)
        assert "API request failed" in result[0].text
        assert "500" in result[0].text
        # Retries belong exclusively to HTTPClient, not the tool generator.
        assert mock_get.call_count == 2

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


class TestRawOpenAPIExecution:
    def test_internal_get_preserves_model_visibility(self, mock_openapi_spec):
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.openapi_spec = mock_openapi_spec
        names = [tool.name for tool in generator.list_tools()]
        assert generator._shorten_tool_name("disabled_endpoint") not in names
        with patch(
            "pdbe_mcp_server.api_tools.HTTPClient.get", return_value={"value": 7}
        ) as get:
            raw = generator.execute_operation("GET", "/disabled", {})
        assert raw["data"] == {"value": 7}
        assert raw["source"].endswith("/disabled")
        assert raw["retrieved_at"]
        get.assert_called_once_with(raw["source"], params=None)
        with pytest.raises(ValueError, match="Unknown read-only"):
            generator.execute_operation("POST", "/disabled", {})

    def test_tool_and_app_use_same_request_executor(self, mock_openapi_spec):
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.openapi_spec = mock_openapi_spec
        tools = generator.list_tools()
        with patch.object(
            generator, "_execute_request", return_value={"data": {"value": 9}}
        ) as execute:
            assert "9" in generator.call_tool(tools[0].name, {"id": "one"})[0].text
            assert generator.execute_operation("GET", "/test/{id}", {"id": "one"})[
                "data"
            ] == {"value": 9}
        assert execute.call_count == 2
        generator.list_tools()
        assert len(generator.tools) == 1

    def test_path_arguments_are_encoded(self, mock_openapi_spec):
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")
        generator.openapi_spec = mock_openapi_spec
        with patch("pdbe_mcp_server.api_tools.HTTPClient.get", return_value={}) as get:
            generator.execute_operation("GET", "/test/{id}", {"id": "a/b?x=1"})
        assert get.call_args.args[0].endswith("/test/a%2Fb%3Fx%3D1")


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
        # Tool name should be shortened and hashed
        expected_name = get_expected_shortened_name("get_test")
        assert tools[0].name == expected_name


class TestShortenToolName:
    """Tests for _shorten_tool_name method."""

    def test_shorten_tool_name_with_common_words(self) -> None:
        """Test that common words are abbreviated or removed."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        # Test removal of 'get', 'api', 'pdb'
        result = generator._shorten_tool_name("get_api_pdb_entry_sequence")
        assert "get" not in result
        assert "api" not in result
        assert "pdb" not in result
        assert "ent" in result  # entry -> ent
        assert "seq" in result  # sequence -> seq

    def test_shorten_tool_name_with_domain_abbreviations(self) -> None:
        """Test domain-specific abbreviations are applied."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        result = generator._shorten_tool_name("get_uniprot_accession_binding_sites")
        assert "unip" in result  # uniprot -> unip
        assert "acc" in result  # accession -> acc
        assert "bind" in result  # binding -> bind

    def test_shorten_tool_name_length_limit(self) -> None:
        """Test that shortened names respect max_length."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        long_name = "get_pdb_entry_sequence_validation_coordinates_information"
        result = generator._shorten_tool_name(long_name, max_length=50)

        assert len(result) <= 50
        # Should have hash suffix
        parts = result.split("_")
        assert len(parts[-1]) == 8  # 8-char hash

    def test_shorten_tool_name_uniqueness(self) -> None:
        """Test that different inputs produce different hashes."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        name1 = "get_pdb_entry_sequence"
        name2 = "get_pdb_entry_sequences"

        result1 = generator._shorten_tool_name(name1)
        result2 = generator._shorten_tool_name(name2)

        # Should be different due to hash
        assert result1 != result2

    def test_shorten_tool_name_hash_format(self) -> None:
        """Test that hash is always 8 hex characters."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        test_names = [
            "get_pdb_entry",
            "get_uniprot_accession_binding_sites",
            "get_secondary_structure_annotations_validation",
        ]

        for name in test_names:
            result = generator._shorten_tool_name(name)
            parts = result.split("_")
            hash_part = parts[-1]
            assert len(hash_part) == 8
            # Verify it's hex
            assert all(c in "0123456789abcdef" for c in hash_part)

    def test_shorten_tool_name_consistency(self) -> None:
        """Test that same input produces same output."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        name = "get_pdb_entry_sequence_validation"
        result1 = generator._shorten_tool_name(name)
        result2 = generator._shorten_tool_name(name)

        assert result1 == result2

    def test_shorten_tool_name_preserves_structure(self) -> None:
        """Test that meaningful structure is preserved."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        result = generator._shorten_tool_name(
            "get_pdb_entry_sequence_validation_coordinates_information"
        )

        # Should contain abbreviated but recognizable parts
        assert "ent" in result
        assert "seq" in result
        assert "val" in result
        assert "coord" in result
        assert "info" in result

    def test_shorten_tool_name_already_short(self) -> None:
        """Test that short names are still hashed."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        short_name = "get_pdb"
        result = generator._shorten_tool_name(short_name, max_length=50)

        # Even short names should have hash suffix
        parts = result.split("_")
        assert len(parts[-1]) == 8

    def test_shorten_tool_name_empty_after_abbreviation(self) -> None:
        """Test handling when all words are removed."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        # Only removable words
        result = generator._shorten_tool_name("get_api_pdb")

        # Should still produce valid output with hash
        assert "_" in result
        parts = result.split("_")
        assert len(parts[-1]) == 8

    def test_shorten_tool_name_complex_pdb_names(self) -> None:
        """Test with realistic PDBe API names."""
        generator = OpenAPIToMCPGenerator("https://example.com/openapi.json")

        test_cases = [
            "get_pdb_entry_sequence",
            "get_uniprot_accession_binding_sites",
            "get_secondary_structure_annotations",
            "get_validation_statistics_outliers",
            "get_compound_interaction_proteins",
            "get_interface_residues_mappings",
        ]

        for name in test_cases:
            result = generator._shorten_tool_name(name, max_length=50)
            assert len(result) <= 50, f"'{name}' produced too long result: {result}"
            # Verify hash is present
            parts = result.split("_")
            assert len(parts[-1]) == 8, f"Missing hash in result: {result}"
