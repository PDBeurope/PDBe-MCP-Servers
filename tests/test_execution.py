"""Deadline and worker-capacity regressions, independent of external APIs."""

import asyncio
import threading

import anyio
import pytest

from pdbe_mcp_server.execution import (
    ToolDeadlineExceeded,
    _jobs,
    run_blocking_tool,
    tool_deadline,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_or_cancellation_preserves_worker_capacity(monkeypatch, cancel):
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "0.1")
    limiter = anyio.to_thread.current_default_thread_limiter()
    original_tokens = limiter.total_tokens
    limiter.total_tokens = 1
    started = threading.Event()
    release = threading.Event()
    queued_ran = threading.Event()

    def slow():
        started.set()
        assert release.wait(3)

    job = asyncio.create_task(run_blocking_tool(slow))
    try:

        async def wait_started():
            while not started.is_set():
                await asyncio.sleep(0.001)

        await asyncio.wait_for(wait_started(), 1)
        if cancel:
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                await job
        else:
            with pytest.raises(ToolDeadlineExceeded, match="deadline"):
                await asyncio.wait_for(job, 1)
        assert limiter.borrowed_tokens == 1

        # Includes the time waiting for a thread. The expired queued function
        # must never run, even once the occupied thread becomes available.
        with pytest.raises(ToolDeadlineExceeded):
            await asyncio.wait_for(run_blocking_tool(queued_ran.set), 1)
        assert not queued_ran.is_set()
        assert limiter.borrowed_tokens == 1
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(*list(_jobs), return_exceptions=True), 1)
        limiter.total_tokens = original_tokens
    assert not queued_ran.is_set()
    assert limiter.borrowed_tokens == 0
    assert await run_blocking_tool(lambda: "recovered") == "recovered"


@pytest.mark.asyncio
async def test_async_tool_children_share_one_deadline(monkeypatch):
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "0.1")

    @tool_deadline
    async def tool():
        await asyncio.sleep(0.06)
        # Starting a child must not grant it another full 100 ms.
        await run_blocking_tool(lambda: threading.Event().wait(0.08))

    try:
        with pytest.raises(ToolDeadlineExceeded):
            await asyncio.wait_for(tool(), 1)
    finally:
        await asyncio.wait_for(asyncio.gather(*list(_jobs), return_exceptions=True), 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
async def test_invalid_deadline_is_rejected_before_work(monkeypatch, value):
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="positive finite"):
        await run_blocking_tool(lambda: pytest.fail("Must not run"))
