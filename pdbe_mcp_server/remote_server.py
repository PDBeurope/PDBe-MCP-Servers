import contextlib
import logging
import os
import sys

import click
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from pdbe_mcp_server.api_tools import get_shared_api_generator
from pdbe_mcp_server.server import (
    build_all_server,
    build_graph_server,
    build_pdbe_api_server,
    build_pdbe_apps_server,
    build_pdbe_search_server,
)

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
    return JSONResponse({"status": "ready"})


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

    # Build backend servers
    graph_server = build_graph_server()
    search_server = build_pdbe_search_server()
    generator = get_shared_api_generator()
    api_server = build_pdbe_api_server(generator)
    apps_server = build_pdbe_apps_server(generator)

    session_managers = {
        "apps": StreamableHTTPSessionManager(
            app=apps_server,
            event_store=None,
            json_response=json_response,
            stateless=True,
        ),
        "graph": StreamableHTTPSessionManager(
            app=graph_server,
            event_store=None,
            json_response=json_response,
            stateless=True,
        ),
        "search": StreamableHTTPSessionManager(
            app=search_server,
            event_store=None,
            json_response=json_response,
            stateless=True,
        ),
        "api": StreamableHTTPSessionManager(
            app=api_server,
            event_store=None,
            json_response=json_response,
            stateless=True,
        ),
    }
    if include_all:
        all_server = build_all_server(
            [api_server, search_server, graph_server, apps_server]
        )
        session_managers["all"] = StreamableHTTPSessionManager(
            app=all_server,
            event_store=None,
            json_response=json_response,
            stateless=True,
        )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with contextlib.AsyncExitStack() as stack:
            for name, manager in session_managers.items():
                await stack.enter_async_context(manager.run())
                logger.info(f"Started session manager for '{name}'")
            yield
            logger.info("Shutting down...")

    def create_handler(manager: StreamableHTTPSessionManager):
        async def handler(scope: Scope, receive: Receive, send: Send):
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

        return handler

    routes: list[Mount | Route] = [
        Mount(f"{ROOT_PREFIX}/apps", app=create_handler(session_managers["apps"])),
        Mount(f"{ROOT_PREFIX}/graph", app=create_handler(session_managers["graph"])),
        Mount(f"{ROOT_PREFIX}/search", app=create_handler(session_managers["search"])),
        Mount(f"{ROOT_PREFIX}/api", app=create_handler(session_managers["api"])),
    ]
    if include_all:
        routes.append(
            Mount(f"{ROOT_PREFIX}/all", app=create_handler(session_managers["all"]))
        )
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
@click.option("--log-level", default="INFO")
@click.option("--json-response", is_flag=True, default=False)
@click.option("--cors-origins", default="*")
@click.option("--workers", default=1, type=int)
@click.option("--reload", is_flag=True, default=False)
@click.option(
    "--all",
    "include_all",
    is_flag=True,
    default=False,
    help="Expose all PDBe tools at the /all endpoint.",
)
def main(
    host, port, log_level, json_response, cors_origins, workers, reload, include_all
):
    # Validate combination
    if reload and workers > 1:
        raise click.UsageError("Cannot use --reload with multiple workers")

    # Pass config via environment
    os.environ["LOG_LEVEL"] = log_level
    os.environ["JSON_RESPONSE"] = str(json_response).lower()
    os.environ["CORS_ORIGINS"] = cors_origins
    os.environ["ALL_SERVERS"] = str(include_all).lower()

    # The module-level app is created before Click invokes main(). Rebuild it
    # when --all is enabled so the selected endpoint is present in this process;
    # workers and reload subprocesses read ALL_SERVERS during module import.
    if include_all:
        global starlette_app
        starlette_app = create_app(include_all=True)

    import uvicorn

    logger.info(f"Starting server on http://{host}{ROOT_PREFIX}:{port}")
    logger.info(
        f"Config: workers={workers}, reload={reload}, log_level={log_level}, "
        f"all_servers={include_all}"
    )

    uvicorn.run(
        "pdbe_mcp_server.remote_server:starlette_app",
        host=host,
        port=port,
        workers=workers if not reload else 1,
        reload=reload,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    sys.exit(main())
