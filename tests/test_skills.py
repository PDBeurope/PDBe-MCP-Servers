import hashlib
import json
from builtins import ExceptionGroup
from unittest.mock import Mock

import anyio
import httpx
import mcp.types as types
import pytest
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.shared.message import SessionMessage
from mcp.types import LATEST_PROTOCOL_VERSION
from starlette.requests import Request
from starlette.responses import JSONResponse

from pdbe_mcp_server.apps import build_pdbe_apps_server
from pdbe_mcp_server.skills import (
    EXTENSION,
    PROTOCOL,
    SkillCatalog,
    run_with_skills,
    skill_http_request,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def request(method, **params):
    return types.JSONRPCRequest(
        jsonrpc="2.0",
        id=1,
        method=method,
        params={
            **params,
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": PROTOCOL,
                "io.modelcontextprotocol/clientCapabilities": {},
            },
        },
    )


def result(catalog, method, **params):
    reply = catalog.dispatch(request(method, **params), "test")
    assert isinstance(reply, types.JSONRPCResponse), reply
    assert reply.result["resultType"] == "complete"
    return reply.result


def test_manifests_match_served_bytes_and_direct_lookup():
    catalog = SkillCatalog()
    entry = result(catalog, "skills/get", uri=catalog.skill_uri)["skill"]
    assert result(catalog, "skills/list")["skills"] == [entry]
    for file in entry["resources"]:
        text = result(catalog, "resources/read", uri=file["uri"])["contents"][0]["text"]
        assert len(text.encode()) == file["size"]
        assert "sha256:" + hashlib.sha256(text.encode()).hexdigest() == file["digest"]


def test_directory_listing_and_discovery():
    catalog = SkillCatalog()
    capabilities = result(catalog, "server/discover")["capabilities"]
    assert capabilities["extensions"][EXTENSION] == {"directoryRead": True}
    children = result(catalog, "resources/directory/read", uri=catalog.root_uri)[
        "resources"
    ]
    assert {item["name"] for item in children} == {"SKILL.md", "references"}
    refs = result(
        catalog, "resources/directory/read", uri=catalog.root_uri + "/references"
    )["resources"]
    assert {item["name"] for item in refs} == {
        "scenes.md",
        "stories.md",
        "builder-api.md",
        "molql-symbols.json",
        "scene.schema.json",
        "story.schema.json",
    }


@pytest.mark.parametrize(
    "method,params",
    [
        ("skills/get", {"uri": "skill://pdbe/missing/SKILL.md"}),
        ("resources/read", {"uri": "skill://pdbe/molview-spec/../secrets"}),
        ("resources/directory/read", {"uri": "skill://pdbe/molview-spec/"}),
        ("skills/list", {"cursor": "invalid"}),
    ],
)
def test_unknown_files_and_invalid_cursors_fail(method, params):
    reply = SkillCatalog().dispatch(request(method, **params), "test")
    assert isinstance(reply, types.JSONRPCError)
    assert reply.error.code == -32602


@pytest.mark.anyio
async def test_modern_http_skills_without_initialize():
    catalog = SkillCatalog()

    async def fallback(scope, receive, send):
        await JSONResponse({"handled_by": "sdk"})(scope, receive, send)

    async def app(scope, receive, send):
        assert await skill_http_request(
            catalog, "pdbe-apps", scope, receive, send, fallback
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/",
            json=request("skills/list").model_dump(by_alias=True),
            headers={"MCP-Protocol-Version": PROTOCOL},
        )
        assert response.status_code == 200
        assert response.json()["result"]["skills"][0]["uri"] == catalog.skill_uri
        bad = request("skills/list").model_dump(by_alias=True)
        bad["params"].pop("_meta")
        response = await client.post(
            "/", json=bad, headers={"MCP-Protocol-Version": PROTOCOL}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == -32602


@pytest.mark.anyio
async def test_modern_http_standard_method_reaches_sdk_with_replayed_body():
    catalog = SkillCatalog()
    forwarded = {}

    async def fallback(scope, receive, send):
        forwarded["protocol"] = dict(scope["headers"])[b"mcp-protocol-version"].decode()
        forwarded["body"] = await Request(scope, receive).json()
        await JSONResponse({"handled_by": "sdk"})(scope, receive, send)

    async def app(scope, receive, send):
        assert await skill_http_request(
            catalog, "pdbe-apps", scope, receive, send, fallback
        )

    payload = request("tools/list").model_dump(by_alias=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/",
            json=payload,
            headers={"MCP-Protocol-Version": PROTOCOL},
        )

    assert response.status_code == 200
    assert response.json() == {"handled_by": "sdk"}
    assert forwarded["protocol"] == LATEST_PROTOCOL_VERSION
    assert forwarded["body"] == payload


@pytest.mark.anyio
@pytest.mark.parametrize("json_response", [True, False])
async def test_modern_http_tools_list_works_through_mcp_sdk(json_response):
    server = build_pdbe_apps_server(Mock())
    manager = StreamableHTTPSessionManager(
        app=server, json_response=json_response, stateless=True
    )

    async def app(scope, receive, send):
        assert await skill_http_request(
            server.skill_catalog,
            server.name,
            scope,
            receive,
            send,
            manager.handle_request,
        )

    def response_payload(response):
        if json_response:
            return response.json()
        return json.loads(
            next(
                line.removeprefix("data: ")
                for line in response.text.splitlines()
                if line.startswith("data: ")
            )
        )

    async with manager.run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            tools_response = await client.post(
                "/",
                json=request("tools/list").model_dump(by_alias=True),
                headers={
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": PROTOCOL,
                },
            )
            tools = response_payload(tools_response)["result"]["tools"]
            app_uri = next(
                tool["_meta"]["ui"]["resourceUri"]
                for tool in tools
                if tool.get("_meta", {}).get("ui", {}).get("resourceUri")
            )
            resources_response = await client.post(
                "/",
                json=request("resources/list").model_dump(by_alias=True),
                headers={
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": PROTOCOL,
                },
            )
            read_response = await client.post(
                "/",
                json=request("resources/read", uri=app_uri).model_dump(by_alias=True),
                headers={
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": PROTOCOL,
                },
            )

            legacy_payload = request("resources/read", uri=app_uri).model_dump(
                by_alias=True
            )
            legacy_payload["params"].pop("_meta")
            legacy_response = await client.post(
                "/",
                json=legacy_payload,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": PROTOCOL,
                },
            )

    assert tools_response.status_code == 200
    assert tools
    assert resources_response.status_code == 200
    assert app_uri in {
        resource["uri"]
        for resource in response_payload(resources_response)["result"]["resources"]
    }
    assert read_response.status_code == 200
    read_result = response_payload(read_response)["result"]
    assert len(read_result["contents"][0]["text"]) > 1000
    assert read_result["resultType"] == "complete"
    assert read_result["ttlMs"] == 300000
    assert read_result["cacheScope"] == "public"

    assert legacy_response.status_code == 200
    legacy_result = response_payload(legacy_response)["result"]
    assert legacy_result["contents"] == read_result["contents"]
    assert not {"resultType", "ttlMs", "cacheScope"} & legacy_result.keys()


@pytest.mark.anyio
async def test_stdio_extension_probe_and_file_read_without_initialize():
    server = build_pdbe_apps_server(Mock())
    to_server, from_client = anyio.create_memory_object_stream(0)
    to_client, from_server = anyio.create_memory_object_stream(0)
    async with anyio.create_task_group() as group:

        async def run():
            await server.run(
                from_client, to_client, server.create_initialization_options()
            )

        group.start_soon(run)
        try:
            with anyio.fail_after(5):
                for query in [
                    request("server/discover"),
                    request("skills/list"),
                    request("resources/read", uri="skill://pdbe/molview-spec/SKILL.md"),
                ]:
                    await to_server.send(SessionMessage(types.JSONRPCMessage(query)))
                    response = (await from_server.receive()).message.root
                    assert isinstance(response, types.JSONRPCResponse)
                    assert response.result["resultType"] == "complete"
        finally:
            group.cancel_scope.cancel()


@pytest.mark.anyio
@pytest.mark.parametrize("closure", ["read", "write", "peer"])
async def test_transport_shutdown_finishes_skills_and_sdk(closure):
    server = build_pdbe_apps_server(Mock())
    to_server, from_client = anyio.create_memory_object_stream(0)
    to_client, from_server = anyio.create_memory_object_stream(0)
    finished = anyio.Event()

    async def run():
        await server.run(
            from_client,
            to_client,
            server.create_initialization_options(),
            stateless=True,
        )
        finished.set()

    async with to_server, from_client, to_client, from_server:
        with anyio.fail_after(5):
            async with anyio.create_task_group() as group:
                group.start_soon(run)
                # A response proves the forwarding loop and SDK are running.
                await to_server.send(
                    SessionMessage(types.JSONRPCMessage(request("skills/list")))
                )
                assert isinstance(
                    (await from_server.receive()).message.root, types.JSONRPCResponse
                )
                if closure == "read":
                    await from_client.aclose()
                else:
                    await (to_client if closure == "write" else from_server).aclose()
                    await to_server.send(
                        SessionMessage(types.JSONRPCMessage(request("skills/list")))
                    )
                await finished.wait()


@pytest.mark.anyio
async def test_skills_forwarding_does_not_hide_unexpected_errors():
    catalog = Mock()
    catalog.handles.side_effect = ValueError("unexpected catalog failure")
    to_server, from_client = anyio.create_memory_object_stream(1)
    to_client, from_server = anyio.create_memory_object_stream(0)

    async def run(receiver, writer, options):
        async with receiver, writer:
            async for _ in receiver:
                pass

    async with to_server, from_client, to_client, from_server:
        await to_server.send(
            SessionMessage(types.JSONRPCMessage(request("skills/list")))
        )
        with anyio.fail_after(5):
            with pytest.raises(ExceptionGroup) as caught:
                await run_with_skills(
                    catalog, "test", run, from_client, to_client, None
                )
        assert any(
            isinstance(error, ValueError) and str(error) == "unexpected catalog failure"
            for error in caught.value.exceptions
        )
