"""Startup, readiness, and shutdown ordering for the production ASGI app."""

import asyncio
import contextlib
import subprocess
import sys
import threading
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from click.testing import CliRunner
from starlette.responses import JSONResponse

from pdbe_mcp_server import remote_server as remote
from pdbe_mcp_server.execution import ToolDeadlineExceeded, _jobs, run_blocking_tool
from pdbe_mcp_server.graph_tools import GraphTools


@pytest.fixture
def resources(monkeypatch):
    monkeypatch.setattr(
        GraphTools, "_get_graph_schema", lambda self: {"nodes": [], "edges": []}
    )
    graph = GraphTools()
    graph.aclose = AsyncMock()
    generator = Mock()
    generator.list_tools.return_value = []
    monkeypatch.setattr(remote, "GraphTools", lambda: graph)
    monkeypatch.setattr(remote, "get_shared_api_generator", lambda: generator)
    close_http = Mock()
    monkeypatch.setattr(remote.HTTPClient, "close_session", close_http)
    return graph, generator, close_http


async def wait_thread_event(event):
    async def wait():
        while not event.is_set():
            await asyncio.sleep(0.001)

    await asyncio.wait_for(wait(), 1)


def test_import_and_app_creation_do_not_fetch_schemas():
    script = """
from unittest.mock import patch
from pdbe_mcp_server.utils import HTTPClient
with patch.object(HTTPClient, 'get', side_effect=AssertionError('Import performed network I/O')):
    from pdbe_mcp_server.remote_server import create_app
    app = create_app(include_all=True)
    assert not app.app.state.ready
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_startup_is_nonblocking_and_readiness_tracks_lifespan(
    monkeypatch, resources
):
    graph, generator, close_http = resources
    started = threading.Event()
    release = threading.Event()
    entered = asyncio.Event()
    stop = asyncio.Event()

    def load_schema():
        started.set()
        assert release.wait(3)
        return generator

    monkeypatch.setattr(remote, "get_shared_api_generator", load_schema)
    app = remote.create_app(include_all=True)

    async def serve():
        async with app.app.router.lifespan_context(app.app):
            entered.set()
            await stop.wait()

    serving = asyncio.create_task(serve())
    try:
        await wait_thread_event(started)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            assert (await client.get(f"{remote.ROOT_PREFIX}/health")).status_code == 200
            assert (await client.get(f"{remote.ROOT_PREFIX}/ready")).status_code == 503
            assert (await client.post(f"{remote.ROOT_PREFIX}/all/")).status_code == 503
            release.set()
            await asyncio.wait_for(entered.wait(), 1)
            assert (await client.get(f"{remote.ROOT_PREFIX}/ready")).status_code == 200
    finally:
        release.set()
        stop.set()
        await asyncio.wait_for(serving, 1)
    assert not app.app.state.ready
    graph.aclose.assert_awaited_once()
    close_http.assert_called_once()


@pytest.mark.asyncio
async def test_failed_startup_cleans_up_resources(monkeypatch, resources):
    graph, _, close_http = resources
    events = []

    class Manager:
        count = 0

        def __init__(self, **kwargs):
            self.number = Manager.count
            Manager.count += 1

        @contextlib.asynccontextmanager
        async def run(self):
            if self.number == 1:
                raise RuntimeError("manager startup failed")
            try:
                yield
            finally:
                events.append("manager stopped")

    monkeypatch.setattr(remote, "StreamableHTTPSessionManager", Manager)
    graph.aclose.side_effect = lambda: events.append("graph closed")
    close_http.side_effect = lambda: events.append("HTTP closed")
    app = remote.create_app()
    with pytest.raises(RuntimeError, match="manager startup failed"):
        async with app.app.router.lifespan_context(app.app):
            pytest.fail("Startup should fail")
    assert not app.app.state.ready
    assert events == ["manager stopped", "graph closed", "HTTP closed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("drain_expires", [False, True])
async def test_shutdown_drains_timed_out_work_before_closing_pools(
    monkeypatch, resources, drain_expires
):
    graph, _, close_http = resources
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setenv(
        "SHUTDOWN_DRAIN_TIMEOUT_SECONDS", "0.05" if drain_expires else "1"
    )
    started = threading.Event()
    release = threading.Event()
    entered = asyncio.Event()
    stop = asyncio.Event()
    events = []

    def work():
        started.set()
        assert release.wait(3)
        events.append("worker finished")

    graph.aclose.side_effect = lambda: events.append("graph closed")
    close_http.side_effect = lambda: events.append("HTTP closed")
    app = remote.create_app()

    async def serve():
        async with app.app.router.lifespan_context(app.app):
            entered.set()
            await stop.wait()

    serving = asyncio.create_task(serve())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(ToolDeadlineExceeded):
            await run_blocking_tool(work)
        assert started.is_set()
        stop.set()
        if drain_expires:
            await asyncio.wait_for(serving, 1)
            close_http.assert_not_called()
            assert "worker finished" not in events
        else:
            # Wait until shutdown reaches its drain, without releasing the worker.
            while app.app.state.ready:
                await asyncio.sleep(0)
            await asyncio.sleep(0)
            close_http.assert_not_called()
            graph.aclose.assert_not_awaited()
            release.set()
            await asyncio.wait_for(serving, 1)
            assert events == ["worker finished", "graph closed", "HTTP closed"]
        assert not app.app.state.ready
    finally:
        release.set()
        stop.set()
        await asyncio.wait_for(serving, 1)
        await asyncio.wait_for(asyncio.gather(*list(_jobs), return_exceptions=True), 1)


@pytest.mark.asyncio
async def test_lifespan_cancellation_still_finishes_cleanup(resources):
    graph, _, close_http = resources
    entered = asyncio.Event()
    closing = asyncio.Event()
    release = asyncio.Event()

    async def close_graph():
        closing.set()
        await release.wait()

    graph.aclose.side_effect = close_graph
    app = remote.create_app()

    async def serve():
        async with app.app.router.lifespan_context(app.app):
            entered.set()
            await asyncio.Event().wait()

    serving = asyncio.create_task(serve())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        serving.cancel()
        await asyncio.wait_for(closing.wait(), 1)
        assert not app.app.state.ready
        close_http.assert_not_called()
        assert not serving.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(serving, 1)
    graph.aclose.assert_awaited_once()
    close_http.assert_called_once()


@pytest.mark.asyncio
async def test_neo4j_close_is_awaited_and_idempotent(monkeypatch):
    monkeypatch.setattr(
        GraphTools, "_get_graph_schema", lambda self: {"nodes": [], "edges": []}
    )
    graph = GraphTools()
    driver = Mock(close=AsyncMock())
    graph._neo4j_driver = driver
    await graph.aclose()
    await graph.aclose()
    driver.close.assert_awaited_once()
    assert graph._neo4j_driver is None


def test_cli_uses_factory_after_options_are_applied(monkeypatch):
    import uvicorn

    run = Mock()
    monkeypatch.setattr(uvicorn, "run", run)
    for variable in [
        "ALL_SERVERS",
        "JSON_RESPONSE",
        "CORS_ORIGINS",
        "LOG_LEVEL",
        "MAX_CONCURRENT_MCP_REQUESTS",
    ]:
        monkeypatch.setenv(variable, "")
    result = CliRunner().invoke(
        remote.main,
        ["--all", "--json-response", "--cors-origins", "https://example.test"],
    )
    assert result.exit_code == 0, result.output
    assert run.call_args.args == ("pdbe_mcp_server.remote_server:create_app",)
    assert run.call_args.kwargs["factory"] is True
    assert remote.os.environ["ALL_SERVERS"] == "true"
    assert remote.os.environ["JSON_RESPONSE"] == "true"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "error", "cancel"])
async def test_overload_rejects_mcp_but_preserves_probes_and_releases_slots(
    monkeypatch, resources, outcome
):
    monkeypatch.setenv("MAX_CONCURRENT_MCP_REQUESTS", "1")
    started = asyncio.Event()
    release = asyncio.Event()
    first = True

    class Manager:
        def __init__(self, **kwargs):
            pass

        @contextlib.asynccontextmanager
        async def run(self):
            yield

        async def handle_request(self, scope, receive, send):
            nonlocal first
            if first:
                first = False
                started.set()
                await release.wait()
                if outcome == "error":
                    raise RuntimeError("simulated failure")
            await JSONResponse({"ok": True})(scope, receive, send)

    monkeypatch.setattr(remote, "StreamableHTTPSessionManager", Manager)
    app = remote.create_app(include_all=True)
    async with app.app.router.lifespan_context(app.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            request = asyncio.create_task(client.post(f"{remote.ROOT_PREFIX}/api/"))
            try:
                await asyncio.wait_for(started.wait(), 1)
                # One limit covers all MCP endpoints, with no effect on probes.
                overloaded = await client.post(f"{remote.ROOT_PREFIX}/all/")
                assert overloaded.status_code == 503
                assert overloaded.headers["Retry-After"] == "1"
                assert (
                    await client.get(f"{remote.ROOT_PREFIX}/health")
                ).status_code == 200
                assert (
                    await client.get(f"{remote.ROOT_PREFIX}/ready")
                ).status_code == 200
                if outcome == "cancel":
                    request.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await request
                else:
                    release.set()
                    response = await asyncio.wait_for(request, 1)
                    assert response.status_code == (500 if outcome == "error" else 200)
                assert (
                    await client.post(f"{remote.ROOT_PREFIX}/api/")
                ).status_code == 200
            finally:
                release.set()
                if not request.done():
                    await request


@pytest.mark.parametrize("override", [False, True])
def test_production_cli_reads_environment_and_allows_flag_overrides(
    monkeypatch, override
):
    import uvicorn

    run = Mock()
    monkeypatch.setattr(uvicorn, "run", run)
    env = {
        "WEB_CONCURRENCY": "3",
        "MAX_CONCURRENT_MCP_REQUESTS": "12",
        "UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN": "60",
        "UVICORN_TIMEOUT_KEEP_ALIVE": "8",
        "LOG_LEVEL": "WARNING",
        "ALL_SERVERS": "true",
    }
    args = ["--workers", "2", "--timeout-graceful-shutdown", "55"] if override else []
    result = CliRunner().invoke(remote.main, args, env=env)
    assert result.exit_code == 0, result.output
    config = run.call_args.kwargs
    assert config["workers"] == (2 if override else 3)
    assert config["timeout_graceful_shutdown"] == (55 if override else 60)
    assert config["timeout_keep_alive"] == 8
    assert config["reload"] is False
    assert config["log_level"] == "warning"


@pytest.mark.parametrize(
    "args",
    [
        ["--workers", "0"],
        ["--max-concurrent-mcp-requests", "0"],
        ["--timeout-graceful-shutdown", "-1"],
        ["--workers", "2", "--reload"],
    ],
)
def test_invalid_production_options_fail_before_start(monkeypatch, args):
    import uvicorn

    run = Mock()
    monkeypatch.setattr(uvicorn, "run", run)
    result = CliRunner().invoke(remote.main, args)
    assert result.exit_code != 0
    run.assert_not_called()
