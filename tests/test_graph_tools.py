"""Tests for graph_tools module."""

from typing import Any
from unittest.mock import MagicMock, patch

from pdbe_mcp_server.graph_tools import GraphTools


class TestGraphTools:
    """Tests for GraphTools class."""

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_initialization(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test GraphTools initialization."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()

        assert tools.graph_schema == mock_graph_schema
        assert len(tools.nodes) == 2
        assert len(tools.edges) == 1
        assert tools.node_dict[1] == "Structure"
        assert tools.node_dict[2] == "Ligand"

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_nodes_strips_html(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test that HTML tags are stripped from node descriptions."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        nodes = tools.get_nodes()

        # Check that HTML tags are stripped
        assert "<b>" not in nodes[0]["description"]
        assert "protein" in nodes[0]["description"]

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_edges_strips_html(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test that HTML tags are stripped from edge descriptions."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        edges = tools.get_edges()

        # Check that HTML tags are stripped
        assert "<i>" not in edges[0]["description"]
        assert "ligand" in edges[0]["description"]

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_format_nodes(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test node formatting."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        formatted = tools.format_nodes()

        assert "Label: Structure" in formatted
        assert "Label: Ligand" in formatted
        assert "pdb_id" in formatted
        assert "PDB identifier" in formatted

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_format_edges(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test edge formatting."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        formatted = tools.format_edges()

        assert "Label: HAS_LIGAND" in formatted
        assert "From: Structure" in formatted
        assert "To: Ligand" in formatted
        assert "count" in formatted

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_node_by_label_found(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test getting node by label when found."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        result = tools.get_node_by_label("Structure")

        assert result is not None
        assert "Structure" in result
        assert "protein" in result

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_node_by_label_not_found(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test getting node by label when not found."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        result = tools.get_node_by_label("NonExistent")

        assert result is None

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_edge_by_label_found(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test getting edge by label when found."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        result = tools.get_edge_by_label("HAS_LIGAND")

        assert result is not None
        assert result["label"] == "HAS_LIGAND"

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_edge_by_label_not_found(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test getting edge by label when not found."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        result = tools.get_edge_by_label("NonExistent")

        assert result is None

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_nodes_without_properties(self, mock_get: MagicMock) -> None:
        """Test formatting nodes without properties."""
        schema = {
            "nodes": [
                {
                    "id": 1,
                    "label": "TestNode",
                    "title": "Test",
                    "description": "Test description",
                    "properties": [],
                }
            ],
            "edges": [],
        }
        mock_get.return_value = schema

        tools = GraphTools()
        formatted = tools.format_nodes()

        assert "Properties: None" in formatted

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_edges_without_properties(self, mock_get: MagicMock) -> None:
        """Test formatting edges without properties."""
        schema = {
            "nodes": [
                {"id": 1, "label": "Node1", "title": "N1", "description": "Desc1"},
                {"id": 2, "label": "Node2", "title": "N2", "description": "Desc2"},
            ],
            "edges": [
                {
                    "label": "TEST_EDGE",
                    "title": "Test",
                    "description": "Test edge",
                    "from": 1,
                    "to": 2,
                    "properties": [],
                }
            ],
        }
        mock_get.return_value = schema

        tools = GraphTools()
        formatted = tools.format_edges()

        assert "Properties: None" in formatted

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_pdbe_graph_nodes_tool(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test getting the graph nodes MCP tool."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        tool = tools.get_pdbe_graph_nodes_tool()

        assert tool.name == "pdbe_graph_nodes"
        assert tool.description is not None
        assert "graph database" in tool.description.lower()
        assert tool.inputSchema["type"] == "object"
        assert tool.inputSchema["additionalProperties"] is False

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_pdbe_graph_edges_tool(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test getting the graph edges MCP tool."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        tool = tools.get_pdbe_graph_edges_tool()

        assert tool.name == "pdbe_graph_edges"
        assert tool.description is not None
        assert "relationship" in tool.description.lower()
        assert tool.inputSchema["type"] == "object"
        assert tool.inputSchema["additionalProperties"] is False

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_format_example_queries(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test formatting example queries."""
        schema_with_examples = {
            **mock_graph_schema,
            "examples": [
                {
                    "query": "Find all structures",
                    "description": "MATCH (s:Structure) RETURN s",
                },
                {
                    "query": "Find ligands",
                    "description": "MATCH (l:Ligand) RETURN l",
                },
            ],
        }
        mock_get.return_value = schema_with_examples

        tools = GraphTools()
        formatted = tools.format_example_queries()

        assert "Question: Find all structures" in formatted
        assert "Query:\nMATCH (s:Structure) RETURN s" in formatted
        assert "Question: Find ligands" in formatted
        assert "Query:\nMATCH (l:Ligand) RETURN l" in formatted

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_format_example_queries_empty(self, mock_get: MagicMock) -> None:
        """Test formatting example queries when no examples exist."""
        schema = {"nodes": [], "edges": [], "examples": []}
        mock_get.return_value = schema

        tools = GraphTools()
        formatted = tools.format_example_queries()

        assert formatted == ""

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_format_example_queries_no_examples_key(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test formatting example queries when examples key is missing."""
        mock_get.return_value = {
            k: v for k, v in mock_graph_schema.items() if k != "examples"
        }

        tools = GraphTools()
        formatted = tools.format_example_queries()

        assert formatted == ""

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_pdbe_graph_example_queries_tool(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test getting the graph example queries MCP tool."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        tool = tools.get_pdbe_graph_example_queries_tool()

        assert tool.name == "pdbe_graph_example_queries"
        assert tool.description is not None
        assert "cypher" in tool.description.lower()
        assert tool.inputSchema["type"] == "object"
        assert tool.inputSchema["additionalProperties"] is False
