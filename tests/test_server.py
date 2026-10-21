"""Tests for server module."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from pdbe_mcp_server.server import (
    ROOT_PREFIX,
    MCPServerFactory,
    build_all_server,
    build_graph_server,
    build_pdbe_api_server,
    build_pdbe_search_server,
    factory,
    main,
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

    @patch("pdbe_mcp_server.server.GraphTools")
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


def test_all_server_is_registered_and_advertised_in_cli():
    assert factory._builders["all"] is build_all_server
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "|all]" in result.output


@pytest.mark.parametrize("explicit_stdio", [False, True])
def test_cli_all_runs_the_aggregate_server_over_stdio(monkeypatch, explicit_stdio):
    server = MagicMock()
    server.run = AsyncMock()
    monkeypatch.setitem(factory._builders, "all", lambda: server)
    streams = (MagicMock(), MagicMock())
    opened = []

    @asynccontextmanager
    async def stdio():
        opened.append(True)
        yield streams

    monkeypatch.setattr("mcp.server.stdio.stdio_server", stdio)
    args = ["--server-type=all"]
    if explicit_stdio:
        args.extend(["--transport", "stdio"])
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    assert opened == [True]
    server.run.assert_awaited_once_with(
        *streams, server.create_initialization_options.return_value
    )


def test_cli_all_has_a_valid_sse_path(monkeypatch):
    server = MagicMock()
    monkeypatch.setitem(factory._builders, "all", lambda: server)
    run = MagicMock()
    monkeypatch.setattr("uvicorn.run", run)
    result = CliRunner().invoke(main, ["--server-type=all", "--transport", "sse"])
    assert result.exit_code == 0, result.output
    run.assert_called_once()
    assert run.call_args.kwargs["root_path"] == f"{ROOT_PREFIX}/all"
