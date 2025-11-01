"""Tests for server module."""

from unittest.mock import MagicMock, patch

import pytest

from pdbe_mcp_server.server import (
    MCPServerFactory,
    build_graph_server,
    build_pdbe_api_server,
    build_pdbe_search_server,
)


class TestMCPServerFactory:
    """Tests for MCPServerFactory class."""

    def test_initialization(self) -> None:
        """Test factory initialization."""
        factory = MCPServerFactory()
        assert factory._builders == {}

    def test_register_builder(self) -> None:
        """Test registering a builder function."""
        factory = MCPServerFactory()

        def mock_builder() -> MagicMock:
            return MagicMock()

        factory.register("test_server", mock_builder)
        assert "test_server" in factory._builders

    def test_create_server(self) -> None:
        """Test creating a server."""
        factory = MCPServerFactory()
        mock_server = MagicMock()

        def mock_builder() -> MagicMock:
            return mock_server

        factory.register("test_server", mock_builder)
        server = factory.create("test_server")

        assert server == mock_server

    def test_create_unregistered_server(self) -> None:
        """Test creating an unregistered server raises error."""
        factory = MCPServerFactory()

        with pytest.raises(ValueError, match="No builder registered"):
            factory.create("nonexistent")

    def test_available_types(self) -> None:
        """Test getting available server types."""
        factory = MCPServerFactory()

        def mock_builder() -> MagicMock:
            return MagicMock()

        factory.register("server1", mock_builder)
        factory.register("server2", mock_builder)

        types = factory.available_types()
        assert len(types) == 2
        assert "server1" in types
        assert "server2" in types


class TestBuildPDBeAPIServer:
    """Tests for build_pdbe_api_server function."""

    @patch("pdbe_mcp_server.server.create_mcp_tools_from_openapi")
    def test_build_pdbe_api_server(self, mock_create_tools: MagicMock) -> None:
        """Test building PDBe API server."""
        mock_generator = MagicMock()
        mock_tools = [MagicMock()]
        mock_create_tools.return_value = (mock_generator, mock_tools)

        server = build_pdbe_api_server()

        assert server.name == "pdbe-api-server"
        mock_create_tools.assert_called_once()


class TestBuildGraphServer:
    """Tests for build_graph_server function."""

    @patch("pdbe_mcp_server.server.graph_tools")
    def test_build_graph_server(self, mock_graph_tools: MagicMock) -> None:
        """Test building graph server."""
        mock_graph_tools.get_pdbe_graph_nodes_tool.return_value = MagicMock()
        mock_graph_tools.get_pdbe_graph_edges_tool.return_value = MagicMock()

        server = build_graph_server()

        assert server.name == "pdbe-graph-server"


class TestBuildPDBeSearchServer:
    """Tests for build_pdbe_search_server function."""

    @patch("pdbe_mcp_server.server.search_tools")
    def test_build_search_server(self, mock_search_tools: MagicMock) -> None:
        """Test building search server."""
        mock_search_tools.get_search_schema_tool.return_value = MagicMock()
        mock_search_tools.get_run_search_query_tool.return_value = MagicMock()

        server = build_pdbe_search_server()

        assert server.name == "pdbe-search-server"
        # Check that instructions are provided
        assert server.instructions is not None
        assert "search" in server.instructions.lower()
