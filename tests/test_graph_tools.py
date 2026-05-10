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
    def test_format_node_relationships(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test relationship verification formatting for selected node labels."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        formatted = tools.format_node_relationships(["Structure", "Ligand"])

        assert "Node: Structure" in formatted
        assert "Status: Found" in formatted
        assert "Outgoing edges:\n  - (Structure)-[:HAS_LIGAND]->(Ligand)" in formatted
        assert "Incoming edges:\n  - None" in formatted
        assert "Node: Ligand" in formatted
        assert "Incoming edges:\n  - (Structure)-[:HAS_LIGAND]->(Ligand)" in formatted

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_format_node_relationships_missing_label(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test relationship verification output for unknown node labels."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        formatted = tools.format_node_relationships(["NonExistent"])

        assert formatted == "Node: NonExistent\nStatus: Not found in schema"

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_format_node_relationships_empty_input(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test relationship verification output for empty input."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        formatted = tools.format_node_relationships([])

        assert "node_labels parameter is required" in formatted

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_format_node_relationships_bidirectional_and_self_loop(
        self, mock_get: MagicMock
    ) -> None:
        """Test bidirectional reverse edges and self-loop relationship notes."""
        schema = {
            "nodes": [
                {"id": 1, "label": "NodeA", "title": "A", "description": "A"},
                {"id": 2, "label": "NodeB", "title": "B", "description": "B"},
            ],
            "edges": [
                {
                    "label": "RELATES_TO",
                    "title": "Relates",
                    "description": "A relates to B",
                    "from": 1,
                    "to": 2,
                    "properties": [],
                },
                {
                    "label": "RELATES_TO",
                    "title": "Relates",
                    "description": "B relates to A",
                    "from": 2,
                    "to": 1,
                    "properties": [],
                },
                {
                    "label": "REFERENCES",
                    "title": "References",
                    "description": "A references A",
                    "from": 1,
                    "to": 1,
                    "properties": [],
                },
            ],
        }
        mock_get.return_value = schema

        tools = GraphTools()
        formatted = tools.format_node_relationships(["NodeA"])

        assert (
            "(NodeA)-[:RELATES_TO]->(NodeB) [bidirectional: reverse edge also exists]"
        ) in formatted
        assert (
            "(NodeB)-[:RELATES_TO]->(NodeA) [bidirectional: reverse edge also exists]"
        ) in formatted
        assert "(NodeA)-[:REFERENCES]->(NodeA) [self-loop]" in formatted

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
    def test_get_pdbe_graph_node_relationships_tool(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test getting the graph node relationships MCP tool."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        tool = tools.get_pdbe_graph_node_relationships_tool()

        assert tool.name == "pdbe_graph_node_relationships"
        assert tool.description is not None
        assert "verify" in tool.description.lower()
        assert tool.inputSchema["type"] == "object"
        assert tool.inputSchema["additionalProperties"] is False
        assert "node_labels" in tool.inputSchema.get("properties", {})
        assert "node_labels" in tool.inputSchema.get("required", [])

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_format_example_queries(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test formatting example queries."""
        schema_with_examples = {
            **mock_graph_schema,
            "examples": [
                {
                    "description": "Find all structures",
                    "query": "MATCH (s:Structure) RETURN s",
                },
                {
                    "description": "Find ligands",
                    "query": "MATCH (l:Ligand) RETURN l",
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

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_get_pdbe_run_cypher_query_tool(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test getting the run Cypher query MCP tool."""
        mock_get.return_value = mock_graph_schema

        tools = GraphTools()
        tool = tools.get_pdbe_run_cypher_query_tool()

        assert tool.name == "pdbe_run_cypher_query"
        assert tool.description is not None
        assert "MATCH" in tool.description or "cypher" in tool.description.lower()
        assert tool.inputSchema["type"] == "object"
        assert tool.inputSchema["additionalProperties"] is False
        assert "cypher_query" in tool.inputSchema.get("properties", {})
        assert "cypher_query" in tool.inputSchema.get("required", [])

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_validate_cypher_query_valid_match(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test query validation with valid MATCH queries."""
        from pdbe_mcp_server.graph_tools import _validate_cypher_query

        valid_queries = [
            "MATCH (s:Structure) RETURN s",
            "OPTIONAL MATCH (s:Structure) WHERE s.pdb_id = '1abc' RETURN s",
            "MATCH (s:Structure)-[:HAS_LIGAND]->(l:Ligand) RETURN s, l",
            "CALL { MATCH (s:Structure) RETURN s } RETURN s",
        ]

        for query in valid_queries:
            is_valid, error = _validate_cypher_query(query)
            assert is_valid, f"Query should be valid: {query}"
            assert error is None

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_validate_cypher_query_invalid_merge(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test query validation rejects MERGE queries."""
        from pdbe_mcp_server.graph_tools import _validate_cypher_query

        is_valid, error = _validate_cypher_query("MERGE (s:Structure {id: 1})")
        assert not is_valid
        assert error is not None

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_validate_cypher_query_invalid_create(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test query validation rejects CREATE queries."""
        from pdbe_mcp_server.graph_tools import _validate_cypher_query

        is_valid, error = _validate_cypher_query(
            "CREATE (s:Structure {id: 1}) RETURN s"
        )
        assert not is_valid
        assert error is not None

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_validate_cypher_query_invalid_delete(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test query validation rejects DELETE queries."""
        from pdbe_mcp_server.graph_tools import _validate_cypher_query

        is_valid, error = _validate_cypher_query("MATCH (s:Structure) DELETE s")
        assert not is_valid
        assert error is not None

    @patch("pdbe_mcp_server.graph_tools.HTTPClient.get")
    def test_validate_cypher_query_invalid_set(
        self, mock_get: MagicMock, mock_graph_schema: dict[str, Any]
    ) -> None:
        """Test query validation rejects SET queries."""
        from pdbe_mcp_server.graph_tools import _validate_cypher_query

        is_valid, error = _validate_cypher_query(
            "MATCH (s:Structure) SET s.title = 'New Title'"
        )
        assert not is_valid
        assert error is not None
