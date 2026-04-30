"""Tests for search_tools module."""

from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from pdbe_mcp_server.search_tools import SearchTools


def get_called_query_params(mock_get: MagicMock) -> dict[str, list[str]]:
    call_args = mock_get.call_args
    assert call_args is not None
    url = call_args.args[0]
    return parse_qs(urlparse(url).query)


class TestSearchTools:
    """Tests for SearchTools class."""

    def test_get_run_search_query_tool(self) -> None:
        """Test getting the run search query MCP tool."""
        tools = SearchTools()
        tool = tools.get_run_search_query_tool()

        assert tool.name == "run_search_query"
        assert tool.description is not None
        assert "search query" in tool.description.lower()
        assert "query" in tool.inputSchema["properties"]
        assert tool.inputSchema["properties"]["query"]["type"] == "string"
        assert "fl" in tool.inputSchema["properties"]
        assert "facet" in tool.inputSchema["properties"]
        assert "group" in tool.inputSchema["properties"]
        assert "query" in tool.inputSchema["required"]

    def test_get_search_schema_tool(self) -> None:
        """Test getting the search schema MCP tool."""
        tools = SearchTools()
        tool = tools.get_search_schema_tool()

        assert tool.name == "get_search_schema"
        assert tool.description is not None
        assert "schema" in tool.description.lower()
        assert tool.inputSchema["type"] == "object"
        assert len(tool.inputSchema["properties"]) == 0

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_get_search_schema(
        self, mock_get: MagicMock, mock_search_schema: dict[str, Any]
    ) -> None:
        """Test getting search schema."""
        mock_get.return_value = mock_search_schema

        tools = SearchTools()
        result = tools.get_search_schema()

        # Check header line
        assert "Field Name;Type;Stored;Indexed;Description" in result

        # Check that fields are present
        assert "pdb_id" in result
        assert "title" in result
        assert "resolution" in result

        # Check data types
        assert "string" in result
        assert "text" in result
        assert "float" in result

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_basic(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test running a basic search query."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {"query": "pdb_id:1cbs"}
        result = tools.run_search_query(arguments)

        # Check metadata
        assert "Number of documents found: 2" in result
        assert "Start index: 0" in result

        # Check document data
        assert "1cbs" in result
        assert "Test Structure 1" in result
        assert "2.5" in result

        params = get_called_query_params(mock_get)
        assert params["q"] == ["pdb_id:1cbs"]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_with_filters(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test running search query with legacy filters alias."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {
            "query": "pdb_id:1cbs",
            "filters": ["pdb_id", "title"],
            "start": 0,
            "rows": 10,
        }
        result = tools.run_search_query(arguments)
        assert "1cbs" in result
        assert "Test Structure 1" in result
        assert "2.5" in result

        # Verify HTTPClient.get was called with correct parameters
        params = get_called_query_params(mock_get)
        assert params["q"] == ["pdb_id:1cbs"]
        assert params["fl"] == ["pdb_id,title"]
        assert params["rows"] == ["10"]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_with_fl(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test running search query with Solr fl."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {
            "query": "*:*",
            "fl": ["pdb_id", "title", "resolution"],
        }
        result = tools.run_search_query(arguments)
        assert "1cbs" in result

        params = get_called_query_params(mock_get)
        assert params["q"] == ["*:*"]
        assert params["fl"] == ["pdb_id,title,resolution"]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_with_fq(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test running search query with Solr filter queries."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {
            "query": "kinase",
            "fq": [
                'experimental_method:"X-ray diffraction"',
                "resolution:[0 TO 2.0]",
            ],
            "start": 0,
            "rows": 10,
        }
        result = tools.run_search_query(arguments)
        assert "1cbs" in result

        params = get_called_query_params(mock_get)
        assert params["q"] == ["kinase"]
        assert params["fq"] == [
            'experimental_method:"X-ray diffraction"',
            "resolution:[0 TO 2.0]",
        ]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_with_structured_fq(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test running search query with structured field filters."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {
            "query": "*:*",
            "fq": {
                "experimental_method": "X-ray diffraction",
                "pdb_id": "1cbs",
            },
        }
        result = tools.run_search_query(arguments)
        assert "1cbs" in result

        call_args = mock_get.call_args
        assert call_args is not None
        params = call_args.kwargs["params"]
        assert params["fq"] == [
            'experimental_method:"X-ray diffraction"',
            "pdb_id:1cbs",
        ]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_with_mixed_structured_fq_list(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test running search query with mixed raw and structured filters."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {
            "query": "*:*",
            "fq": [
                {"experimental_method": '"X-ray diffraction"'},
                {"pdb_id": "1cbs"},
                "resolution:[0 TO 2.0]",
            ],
        }
        result = tools.run_search_query(arguments)
        assert "1cbs" in result

        call_args = mock_get.call_args
        assert call_args is not None
        params = call_args.kwargs["params"]
        assert params["fq"] == [
            'experimental_method:"X-ray diffraction"',
            "pdb_id:1cbs",
            "resolution:[0 TO 2.0]",
        ]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_with_sort(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test running search query with sorting."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {
            "query": "resolution:[0 TO 2]",
            "sort": "resolution asc",
            "start": 0,
            "rows": 20,
        }
        result = tools.run_search_query(arguments)

        assert "1cbs" in result
        assert "Test Structure 1" in result
        assert "2.5" in result

        # Verify sort parameter was passed
        params = get_called_query_params(mock_get)
        assert params["sort"] == ["resolution asc"]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_list_values(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test that list values in documents are properly formatted."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {"query": "*:*"}
        result = tools.run_search_query(arguments)

        # Check that list values are joined
        assert "Test Structure 2" in result or "Alternative Title" in result

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_default_parameters(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test search query with default parameters."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {"query": "*:*"}
        result = tools.run_search_query(arguments)

        assert "1cbs" in result
        assert "Test Structure 1" in result
        assert "2.5" in result

        # Verify default parameters
        params = get_called_query_params(mock_get)
        assert params["start"] == ["0"]
        assert params["rows"] == ["10"]
        assert "sort" not in params  # Should not be present if not specified

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_with_facets(self, mock_get: MagicMock) -> None:
        """Test running search query with Solr facets."""
        mock_get.return_value = {
            "response": {"numFound": 0, "start": 0, "docs": []},
            "facet_counts": {
                "facet_fields": {
                    "experimental_method": [
                        "X-ray diffraction",
                        10,
                        "Electron microscopy",
                        5,
                    ]
                }
            },
        }

        tools = SearchTools()
        arguments = {
            "query": "*:*",
            "facet": True,
            "facet_fields": ["experimental_method"],
            "facet_mincount": 1,
        }
        result = tools.run_search_query(arguments)

        assert "Facet counts:" in result
        assert "experimental_method:" in result
        assert "X-ray diffraction" in result

        params = get_called_query_params(mock_get)
        assert params["facet"] == ["true"]
        assert params["facet.field"] == ["experimental_method"]
        assert params["facet.mincount"] == ["1"]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_with_grouping(self, mock_get: MagicMock) -> None:
        """Test running search query with Solr grouping."""
        mock_get.return_value = {
            "response": {"numFound": 0, "start": 0, "docs": []},
            "grouped": {
                "experimental_method": {
                    "matches": 2,
                    "groups": [
                        {
                            "groupValue": "X-ray diffraction",
                            "doclist": {
                                "numFound": 1,
                                "start": 0,
                                "docs": [{"pdb_id": "1cbs"}],
                            },
                        }
                    ],
                }
            },
        }

        tools = SearchTools()
        arguments = {
            "query": "*:*",
            "group": True,
            "group_field": "experimental_method",
            "group_limit": 3,
        }
        result = tools.run_search_query(arguments)

        assert "Grouped results:" in result
        assert "experimental_method:" in result
        assert "X-ray diffraction" in result

        params = get_called_query_params(mock_get)
        assert params["group"] == ["true"]
        assert params["group.field"] == ["experimental_method"]
        assert params["group.limit"] == ["3"]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_with_additional_params(
        self, mock_get: MagicMock, mock_search_response: dict[str, Any]
    ) -> None:
        """Test pass-through Solr params."""
        mock_get.return_value = mock_search_response

        tools = SearchTools()
        arguments = {
            "query": "text:*kinase*",
            "params": {
                "defType": "edismax",
                "qf": "title text",
                "debug": True,
            },
        }
        tools.run_search_query(arguments)

        params = get_called_query_params(mock_get)
        assert params["q"] == ["text:*kinase*"]
        assert params["defType"] == ["edismax"]
        assert params["qf"] == ["title text"]
        assert params["debug"] == ["True"]

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_invalid_response(self, mock_get: MagicMock) -> None:
        """Test handling of invalid search response."""
        mock_get.return_value = {"invalid": "data"}

        tools = SearchTools()
        arguments = {"query": "test"}

        with pytest.raises(Exception, match="Invalid response from search service"):
            tools.run_search_query(arguments)

    @patch("pdbe_mcp_server.search_tools.HTTPClient.get")
    def test_run_search_query_empty_results(self, mock_get: MagicMock) -> None:
        """Test search query with no results."""
        mock_get.return_value = {"response": {"numFound": 0, "start": 0, "docs": []}}

        tools = SearchTools()
        arguments = {"query": "nonexistent"}
        result = tools.run_search_query(arguments)

        assert "Number of documents found: 0" in result
        assert "Documents:" in result
