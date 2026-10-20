import asyncio
import contextlib
import logging
import math
import os
import sys

import anyio
import click
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from pdbe_mcp_server.api_tools import get_shared_api_generator
from pdbe_mcp_server.execution import (
    drain_blocking_tools,
    run_blocking_tool,
    tool_timeout_seconds,
)
from pdbe_mcp_server.graph_tools import GraphTools
from pdbe_mcp_server.server import (
    build_all_server,
    build_graph_server,
    build_pdbe_api_server,
    build_pdbe_apps_server,
    build_pdbe_search_server,
)
from pdbe_mcp_server.utils import HTTPClient

logger = logging.getLogger(__name__)
ROOT_PREFIX = os.getenv("ROOT_PREFIX", "")


# -------------------------
# Helpers
# -------------------------
def parse_cors_origins(origins_str: str) -> list[str]:
    if origins_str == "*":
        return ["*"]
    return [o.strip() for o in origins_str.split(",") if o.strip()] or ["*"]


async def handle_health(request) -> JSONResponse:
    return JSONResponse({"status": "healthy"})


async def handle_ready(request) -> JSONResponse:
    ready = getattr(request.app.state, "ready", False)
    return JSONResponse(
        {"status": "ready" if ready else "not ready"},
        status_code=200 if ready else 503,
    )


# -------------------------
# App Factory
# -------------------------
def create_app(include_all: bool | None = None) -> CORSMiddleware:
    if include_all is None:
        include_all = os.getenv("ALL_SERVERS", "false").lower() == "true"

    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    json_response = os.getenv("JSON_RESPONSE", "false").lower() == "true"
    cors_origins_str = os.getenv("CORS_ORIGINS", "*")
    allowed_origins = parse_cors_origins(cors_origins_str)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    session_managers: dict[str, StreamableHTTPSessionManager] = {}
    request_limiter: anyio.CapacityLimiter | None = None

    def build_backends():
        # Includes schema downloads and indexing: run once in a startup worker,
        # not during import or on the serving event loop.
        graph = GraphTools()
        generator = get_shared_api_generator()
        servers = {
            "graph": build_graph_server(graph),
            "search": build_pdbe_search_server(),
            "api": build_pdbe_api_server(generator),
            "apps": build_pdbe_apps_server(generator),
        }
        if include_all:
            servers["all"] = build_all_server(list(servers.values()))
        return graph, servers

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        nonlocal request_limiter
        app.state.ready = False
        graph = None
        # Validate before allocating resources, including for invalid tool config.
        tool_timeout_seconds()
        drain_timeout = float(os.getenv("SHUTDOWN_DRAIN_TIMEOUT_SECONDS", "30"))
        if not math.isfinite(drain_timeout) or drain_timeout <= 0:
            raise ValueError(
                "SHUTDOWN_DRAIN_TIMEOUT_SECONDS must be positive and finite"
            )
        max_requests = int(os.getenv("MAX_CONCURRENT_MCP_REQUESTS", "64"))
        if max_requests < 1:
            raise ValueError("MAX_CONCURRENT_MCP_REQUESTS must be a positive integer")
        request_limiter = anyio.CapacityLimiter(max_requests)

        async def cleanup():
            drained = await drain_blocking_tools(drain_timeout)
            try:
                if graph is not None:
                    await graph.aclose()
            finally:
                if drained:
                    # Closing pooled sockets is synchronous too.
                    from anyio.to_thread import run_sync

                    await run_sync(HTTPClient.close_session)
                else:
                    logger.warning(
                        "Worker drain exceeded %.1fs; leaving HTTP pools open "
                        "for active workers until process exit",
                        drain_timeout,
                    )

        try:
            graph, servers = await run_blocking_tool(build_backends)
            async with contextlib.AsyncExitStack() as stack:
                for name, server in servers.items():
                    manager = StreamableHTTPSessionManager(
                        app=server,
                        event_store=None,
                        json_response=json_response,
                        stateless=True,
                    )
                    session_managers[name] = manager
                    await stack.enter_async_context(manager.run())
                    logger.info("Started session manager for '%s'", name)
                app.state.ready = True
                try:
                    yield
                finally:
                    app.state.ready = False
                    logger.info("Shutting down...")
        finally:
            app.state.ready = False
            session_managers.clear()
            request_limiter = None
            # Retain cleanup if the ASGI lifespan task is cancelled. The worker
            # drain has its own bounded wait and does not cancel live threads.
            cleanup_task = asyncio.create_task(cleanup())
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                await cleanup_task
                raise

    def create_handler(name: str):
        async def handler(scope: Scope, receive: Receive, send: Send):
            if not app.state.ready:
                await JSONResponse({"error": "Server is not ready"}, status_code=503)(
                    scope, receive, send
                )
                return
            # Limit MCP requests separately from health routes. Applying a
            # Uvicorn-wide limit here would also reject Kubernetes probes.
            limiter = request_limiter
            assert limiter is not None
            try:
                limiter.acquire_nowait()
            except anyio.WouldBlock:
                await JSONResponse(
                    {"error": "Server is busy; retry later"},
                    status_code=503,
                    headers={"Retry-After": "1"},
                )(scope, receive, send)
                return
            manager = session_managers[name]
            try:
                await manager.handle_request(scope, receive, send)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [("content-type", "application/json")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"error": "Internal server error"}',
                    }
                )
            finally:
                limiter.release()

        return handler

    routes: list[Mount | Route] = [
        Mount(f"{ROOT_PREFIX}/apps", app=create_handler("apps")),
        Mount(f"{ROOT_PREFIX}/graph", app=create_handler("graph")),
        Mount(f"{ROOT_PREFIX}/search", app=create_handler("search")),
        Mount(f"{ROOT_PREFIX}/api", app=create_handler("api")),
    ]
    if include_all:
        routes.append(Mount(f"{ROOT_PREFIX}/all", app=create_handler("all")))
    routes.extend(
        [
            Route(f"{ROOT_PREFIX}/health", endpoint=handle_health),
            Route(f"{ROOT_PREFIX}/ready", endpoint=handle_ready),
        ]
    )

    app = Starlette(
        debug=(log_level == logging.DEBUG),
        routes=routes,
        lifespan=lifespan,
    )
    app.state.ready = False

    return CORSMiddleware(
        app,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        expose_headers=["Mcp-Session-Id"],
    )


starlette_app = create_app()


@click.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8000)
@click.option("--log-level", default="INFO", envvar="LOG_LEVEL")
@click.option("--json-response", is_flag=True, default=False, envvar="JSON_RESPONSE")
@click.option("--cors-origins", default="*", envvar="CORS_ORIGINS")
@click.option(
    "--workers", default=1, type=click.IntRange(min=1), envvar="WEB_CONCURRENCY"
)
@click.option(
    "--max-concurrent-mcp-requests",
    default=64,
    type=click.IntRange(min=1),
    envvar="MAX_CONCURRENT_MCP_REQUESTS",
    help="Maximum concurrent MCP requests per worker; health routes are exempt.",
)
@click.option(
    "--timeout-graceful-shutdown",
    default=50,
    type=click.IntRange(min=0),
    envvar="UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN",
    help="Seconds to let active requests finish before lifespan shutdown.",
)
@click.option(
    "--timeout-keep-alive",
    default=5,
    type=click.IntRange(min=0),
    envvar="UVICORN_TIMEOUT_KEEP_ALIVE",
)
@click.option("--reload", is_flag=True, default=False)
@click.option(
    "--all",
    "include_all",
    is_flag=True,
    default=False,
    envvar="ALL_SERVERS",
    help="Expose all PDBe tools at the /all endpoint.",
)
def main(
    host,
    port,
    log_level,
    json_response,
    cors_origins,
    workers,
    max_concurrent_mcp_requests,
    timeout_graceful_shutdown,
    timeout_keep_alive,
    reload,
    include_all,
):
    # Validate combination
    if reload and workers > 1:
        raise click.UsageError("Cannot use --reload with multiple workers")

    # Pass config via environment
    os.environ["LOG_LEVEL"] = log_level
    os.environ["JSON_RESPONSE"] = str(json_response).lower()
    os.environ["CORS_ORIGINS"] = cors_origins
    os.environ["ALL_SERVERS"] = str(include_all).lower()
    os.environ["MAX_CONCURRENT_MCP_REQUESTS"] = str(max_concurrent_mcp_requests)

    import uvicorn

    logger.info(f"Starting server on http://{host}{ROOT_PREFIX}:{port}")
    logger.info(
        f"Config: workers={workers}, reload={reload}, log_level={log_level}, "
        f"all_servers={include_all}"
    )

    uvicorn.run(
        "pdbe_mcp_server.remote_server:create_app",
        factory=True,
        host=host,
        port=port,
        workers=workers if not reload else 1,
        reload=reload,
        log_level=log_level.lower(),
        timeout_graceful_shutdown=timeout_graceful_shutdown,
        timeout_keep_alive=timeout_keep_alive,
    )


if __name__ == "__main__":
    sys.exit(main())
