"""Deadlines shared by async tools and their synchronous HTTP operations."""

import asyncio
import math
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, Awaitable, Callable, Iterator, ParamSpec, TypeVar

import requests
from anyio.to_thread import run_sync

T = TypeVar("T")
P = ParamSpec("P")

_deadline: ContextVar[float | None] = ContextVar("pdbe_tool_deadline", default=None)
# Keep shielded jobs alive until they finish, even after their caller times out.
_jobs: set[asyncio.Task[Any]] = set()


class ToolDeadlineExceeded(requests.Timeout):
    """The overall tool budget, including queueing and retries, has expired."""


def tool_timeout_seconds() -> float:
    value = float(os.getenv("TOOL_TIMEOUT_SECONDS", "45"))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("TOOL_TIMEOUT_SECONDS must be a positive finite number")
    return value


@contextmanager
def request_budget() -> Iterator[None]:
    """Nested work inherits the caller's budget rather than resetting it."""
    deadline = _deadline.get()
    token = _deadline.set(
        deadline if deadline is not None else time.monotonic() + tool_timeout_seconds()
    )
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining_seconds() -> float:
    deadline = _deadline.get()
    if deadline is None:
        raise RuntimeError("No active request budget")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ToolDeadlineExceeded(
            "Tool deadline exceeded; upstream work took too long"
        )
    return remaining


def _job_done(job: asyncio.Task[Any]) -> None:
    _jobs.discard(job)
    if not job.cancelled():
        job.exception()  # Retrieve late exceptions after a caller has timed out.


async def drain_blocking_tools(timeout: float) -> bool:
    """Wait for this event loop's workers without cancelling running threads."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Worker drain timeout must be positive and finite")
    loop = asyncio.get_running_loop()
    jobs = {job for job in _jobs if job.get_loop() is loop and not job.done()}
    if not jobs:
        return True
    _, pending = await asyncio.wait(jobs, timeout=timeout)
    return not pending


async def run_blocking_tool(function: Callable[..., T], *args: Any) -> T:
    """Bound caller latency without releasing capacity for a running thread.

    Cancellation cannot kill a Python thread. Shield the worker task so AnyIO's
    limiter stays acquired until the actual work finishes. An expired queued
    job checks its deadline before invoking the function.
    """
    with request_budget():

        def execute() -> T:
            remaining_seconds()
            result = function(*args)
            remaining_seconds()
            return result

        budget = remaining_seconds()
        job = asyncio.create_task(run_sync(execute))
        _jobs.add(job)
        job.add_done_callback(_job_done)
        try:
            return await asyncio.wait_for(asyncio.shield(job), budget)
        except asyncio.TimeoutError as error:
            raise ToolDeadlineExceeded(
                "Tool deadline exceeded; upstream work took too long"
            ) from error


def tool_deadline(function: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Apply one budget to an async tool, including all of its child fetches."""

    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        with request_budget():
            try:
                return await asyncio.wait_for(
                    function(*args, **kwargs), remaining_seconds()
                )
            except asyncio.TimeoutError as error:
                raise ToolDeadlineExceeded(
                    "Tool deadline exceeded; upstream work took too long"
                ) from error

    return wrapped
