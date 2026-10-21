"""Skills extension catalog and a narrow adapter for the legacy MCP SDK.

The 2026 resource/skill surface is stateless. Existing tool/App operations keep
their SDK-managed initialized transport; we do not claim a full SDK migration.
"""

import hashlib
import json
import logging
from importlib.metadata import version
from pathlib import Path
from typing import Any

import anyio
import mcp.types as types
import yaml
from mcp.shared.message import SessionMessage
from mcp.types import LATEST_PROTOCOL_VERSION
from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import JSONResponse

from pdbe_mcp_server.mvs import BuildMvsInput, BuildStoryInput

EXTENSION = "io.modelcontextprotocol/skills"
PROTOCOL = "2026-07-28"
METHODS = {"server/discover", "skills/list", "skills/get", "resources/directory/read"}


def frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("Skill must begin with YAML frontmatter")
    end = lines[1:].index("---") + 1
    result = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(result, dict) or not all(
        isinstance(result.get(k), str) and result[k].strip()
        for k in ("name", "description")
    ):
        raise ValueError("Skill frontmatter requires name and description")
    return result


class SkillCatalog:
    def __init__(self):
        root = Path(__file__).parent / "skills" / "molview-spec"
        self.root_uri = "skill://pdbe/molview-spec"
        self.files = {
            f"{self.root_uri}/{path.relative_to(root).as_posix()}": path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }
        for filename, model in (("scene", BuildMvsInput), ("story", BuildStoryInput)):
            self.files[f"{self.root_uri}/references/{filename}.schema.json"] = (
                json.dumps(model.model_json_schema(), indent=2) + "\n"
            ).encode()
        self.skill_uri = self.root_uri + "/SKILL.md"
        self.frontmatter = frontmatter(self.files[self.skill_uri].decode("utf-8"))
        if self.frontmatter["name"] != self.root_uri.rsplit("/", 1)[-1]:
            raise ValueError("Skill name must match its directory")

    def entry(self) -> dict[str, Any]:
        return {
            "uri": self.skill_uri,
            "frontmatter": self.frontmatter,
            "resources": [
                {
                    "uri": uri,
                    "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                }
                for uri, data in sorted(self.files.items())
            ],
        }

    def resources(self) -> list[types.Resource]:
        return [
            types.Resource(
                uri=AnyUrl(uri),
                name=self.frontmatter["name"]
                if uri == self.skill_uri
                else uri.rsplit("/", 1)[-1],
                description=self.frontmatter["description"]
                if uri == self.skill_uri
                else None,
                mimeType="application/json"
                if uri.endswith(".json")
                else "text/markdown",
            )
            for uri in sorted(self.files)
        ]

    def read(self, uri: str) -> dict[str, Any]:
        if uri not in self.files:
            raise ValueError("Unknown skill file")
        return {
            "uri": uri,
            "mimeType": "application/json"
            if uri.endswith(".json")
            else "text/markdown",
            "text": self.files[uri].decode("utf-8"),
        }

    def handles(self, request: types.JSONRPCRequest) -> bool:
        params = request.params or {}
        meta = params.get("_meta")
        return request.method in METHODS or (
            isinstance(meta, dict)
            and meta.get("io.modelcontextprotocol/protocolVersion") == PROTOCOL
            and request.method in {"resources/list", "resources/read"}
        )

    def dispatch(
        self, request: types.JSONRPCRequest, server_name: str
    ) -> types.JSONRPCResponse | types.JSONRPCError:
        try:
            params = request.params or {}
            meta = params.get("_meta")
            if (
                not isinstance(meta, dict)
                or meta.get("io.modelcontextprotocol/protocolVersion") != PROTOCOL
                or not isinstance(
                    meta.get("io.modelcontextprotocol/clientCapabilities"), dict
                )
            ):
                raise ValueError(
                    "Skills requests require 2026-07-28 protocolVersion and clientCapabilities in params._meta"
                )
            if params.get("cursor") is not None:
                raise ValueError("Invalid cursor; this catalog fits in one page")
            method = request.method
            if method == "server/discover":
                data = {
                    "supportedVersions": [PROTOCOL],
                    "capabilities": {
                        "resources": {},
                        "extensions": {EXTENSION: {"directoryRead": True}},
                    },
                    "instructions": "This stateless surface serves PDBe skills and their resource files. Tool and App calls use the existing initialized MCP transport.",
                }
            elif method == "skills/list":
                data = {"skills": [self.entry()]}
            elif method == "skills/get":
                if params.get("uri") != self.skill_uri:
                    raise ValueError("Unknown skill URI")
                data = {"skill": self.entry()}
            elif method == "resources/read":
                data = {"contents": [self.read(params.get("uri", ""))]}
            elif method == "resources/list":
                data = {
                    "resources": [
                        r.model_dump(mode="json", by_alias=True, exclude_none=True)
                        for r in self.resources()
                    ]
                }
            elif method == "resources/directory/read":
                uri = params.get("uri", "")
                directories = {file.rsplit("/", 1)[0] for file in self.files} | {
                    self.root_uri
                }
                if uri not in directories:
                    raise ValueError("Unknown skill directory")
                children: dict[str, dict[str, str]] = {}
                for file in self.files:
                    if file.startswith(uri + "/"):
                        name, separator, _ = file[len(uri) + 1 :].partition("/")
                        child = uri + "/" + name
                        children[child] = {
                            "uri": child,
                            "name": name,
                            "mimeType": "inode/directory"
                            if separator
                            else self.read(child)["mimeType"],
                        }
                data = {"resources": list(children.values())}
            else:
                return types.JSONRPCError(
                    jsonrpc="2.0",
                    id=request.id,
                    error=types.ErrorData(
                        code=-32601,
                        message="Method not available on the Skills surface",
                    ),
                )
            return types.JSONRPCResponse(
                jsonrpc="2.0",
                id=request.id,
                result={
                    **data,
                    "resultType": "complete",
                    "ttlMs": 300000,
                    "cacheScope": "public",
                    "_meta": {
                        "io.modelcontextprotocol/serverInfo": {
                            "name": server_name,
                            "version": version("pdbe-mcp-server"),
                        }
                    },
                },
            )
        except (ValueError, TypeError, KeyError):
            return types.JSONRPCError(
                jsonrpc="2.0",
                id=request.id,
                error=types.ErrorData(
                    code=-32602,
                    message="Invalid skill request parameters or unknown skill resource",
                ),
            )


async def run_with_skills(
    catalog,
    server_name,
    run,
    read_stream,
    write_stream,
    initialization_options,
    **kwargs,
):
    """Intercept extension messages before the SDK's closed request union."""
    sender, receiver = anyio.create_memory_object_stream(0)

    async def forward():
        async with sender:
            try:
                async for message in read_stream:
                    request = (
                        message.message.root
                        if isinstance(message, SessionMessage)
                        else None
                    )
                    if isinstance(request, types.JSONRPCRequest) and catalog.handles(
                        request
                    ):
                        reply = catalog.dispatch(request, server_name)
                        await write_stream.send(
                            SessionMessage(types.JSONRPCMessage(reply))
                        )
                    else:
                        await sender.send(message)
            except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                # Stateless HTTP terminates its transport after each response.
                # Close sender so the SDK sees EOF and cancels pending handlers.
                logging.getLogger(__name__).debug("Skills forwarding stream closed")

    async with anyio.create_task_group() as group:
        group.start_soon(forward)
        try:
            await run(receiver, write_stream.clone(), initialization_options, **kwargs)
        finally:
            group.cancel_scope.cancel()


async def skill_http_request(
    catalog, server_name, scope, receive, send, fallback
) -> bool:
    """Handle modern skill requests before the SDK's legacy HTTP-version check."""
    headers = dict(scope.get("headers", []))
    if headers.get(b"mcp-protocol-version") != PROTOCOL.encode():
        return False
    if scope["method"] != "POST":
        await JSONResponse(
            {"error": "The Skills surface supports POST requests"}, status_code=405
        )(scope, receive, send)
        return True
    try:
        body = await Request(scope, receive).body()
        if len(body) > 65536:
            raise ValueError("Request too large")
        request = types.JSONRPCRequest.model_validate_json(body)
        if not catalog.handles(request):
            forwarded_scope = dict(scope)
            forwarded_scope["headers"] = [
                (
                    name,
                    LATEST_PROTOCOL_VERSION.encode()
                    if name.lower() == b"mcp-protocol-version"
                    else value,
                )
                for name, value in scope.get("headers", [])
            ]
            replay_body = True

            async def replay_receive():
                nonlocal replay_body
                if replay_body:
                    replay_body = False
                    return {
                        "type": "http.request",
                        "body": body,
                        "more_body": False,
                    }
                return await receive()

            await fallback(forwarded_scope, replay_receive, send)
            return True
        reply = catalog.dispatch(request, server_name)
        status = 400 if isinstance(reply, types.JSONRPCError) else 200
        response = reply.model_dump(mode="json", by_alias=True, exclude_none=True)
    except ValueError:
        response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid skill request"},
        }
        status = 400
    await JSONResponse(response, status_code=status)(scope, receive, send)
    return True
