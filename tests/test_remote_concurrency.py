"""Slow synchronous tools must not stall other requests on a single worker."""

import asyncio
import threading
from unittest.mock import Mock

import httpx
import mcp.types as types
import pytest
from sse_starlette.sse import AppStatus

from pdbe_mcp_server import remote_server as remote
from pdbe_mcp_server import server
from pdbe_mcp_server.graph_tools import GraphTools


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [False, True])
@pytest.mark.parametrize(
    "slow_tool", ["slow_api", "get_pdbe_search_schema", "run_pdbe_search_query"]
)
async def test_slow_tool_leaves_remote_server_responsive(
    monkeypatch, slow_tool, timeout
):
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "0.2" if timeout else "3")
    # sse-starlette keeps this event globally; pytest uses a loop per case.
    monkeypatch.setattr(AppStatus, "should_exit_event", None)
    started = threading.Event()
    release = threading.Event()

    def block(*args):
        started.set()
        if not release.wait(3):
            raise RuntimeError("Test did not release the slow tool")
        return "finished"

    def api_call(name, arguments):
        if name == "slow_api":
            block()
        return [types.TextContent(type="text", text="ok")]

    generator = Mock()
    generator.list_tools.return_value = [
        types.Tool(name=name, inputSchema={"type": "object"})
        for name in ["slow_api", "fast_api"]
    ]
    generator.call_tool.side_effect = api_call

    monkeypatch.setattr(
        GraphTools, "_get_graph_schema", lambda self: {"nodes": [], "edges": []}
    )
    monkeypatch.setattr(remote, "get_shared_api_generator", lambda: generator)
    monkeypatch.setattr(server.search_tools, "get_search_schema", block)
    monkeypatch.setattr(server.search_tools, "run_search_query", block)
    app = remote.create_app(include_all=True)
    prefix = remote.ROOT_PREFIX

    async with app.app.router.lifespan_context(app.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:

            async def rpc(method, params=None, allow_error=False):
                response = await client.post(
                    f"{prefix}/all/",
                    headers={"Accept": "application/json, text/event-stream"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                        "params": params or {},
                    },
                )
                assert response.status_code == 200
                assert '"error"' not in response.text
                if not allow_error:
                    assert '"isError":true' not in response.text
                return response

            # Prime the real aggregate server's tool registry before starting.
            await rpc("tools/list")
            arguments = {"query": "*:*"} if slow_tool == "run_pdbe_search_query" else {}
            slow = asyncio.create_task(
                rpc(
                    "tools/call",
                    {"name": slow_tool, "arguments": arguments},
                    allow_error=timeout,
                )
            )
            try:

                async def wait_started():
                    while not started.is_set():
                        await asyncio.sleep(0.005)

                await asyncio.wait_for(wait_started(), timeout=1)
                assert (
                    not slow.done()
                ), "Slow tool blocked the event loop until completion"
                health, ping, fast = await asyncio.wait_for(
                    asyncio.gather(
                        client.get(f"{prefix}/health"),
                        rpc("ping"),
                        rpc("tools/call", {"name": "fast_api", "arguments": {}}),
                    ),
                    timeout=1,
                )
                assert health.json() == {"status": "healthy"}
                assert ping.status_code == fast.status_code == 200
                assert not slow.done()
                if timeout:
                    result = await asyncio.wait_for(slow, 1)
                    assert '"isError":true' in result.text
                    assert "deadline exceeded" in result.text
                    assert not release.is_set()
            finally:
                release.set()
                await slow
                # A response timeout deliberately leaves the worker alive.
                from pdbe_mcp_server.execution import _jobs

                await asyncio.gather(*list(_jobs), return_exceptions=True)
