"""One retry layer, bounded backoff, and thread-owned HTTP sessions."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pytest
import requests

from pdbe_mcp_server.execution import ToolDeadlineExceeded
from pdbe_mcp_server.utils import HTTPClient


def response(status=200, headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = {"ok": True}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(response=result)
    return result


@pytest.mark.parametrize("status,attempts", [(503, 3), (429, 3), (404, 1)])
def test_retry_count_is_bounded(status, attempts):
    session = Mock()
    replies = [response(status) for _ in range(attempts)]
    session.get.side_effect = replies
    with patch.object(HTTPClient, "_get_session", return_value=session):
        with pytest.raises(requests.HTTPError):
            HTTPClient.get("https://example.test", retry_delay=0)
    assert session.get.call_count == attempts
    for reply in replies:
        reply.close.assert_called_once()


def test_connection_timeout_is_retried_but_post_is_not():
    session = Mock()
    session.get.side_effect = [requests.Timeout("slow"), response()]
    session.post.side_effect = requests.ConnectionError("offline")
    with patch.object(HTTPClient, "_get_session", return_value=session):
        assert HTTPClient.get("https://example.test", retry_delay=0) == {"ok": True}
        with pytest.raises(requests.ConnectionError):
            HTTPClient.post("https://example.test")
    assert session.get.call_count == 2
    assert session.post.call_count == 1


def test_retry_attempt_inherits_remaining_budget(monkeypatch):
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "45")
    clock = [0.0]
    session = Mock()

    def get(*args, **kwargs):
        if session.get.call_count == 1:
            clock[0] += 20
            return response(503)
        return response()

    session.get.side_effect = get
    with (
        patch.object(HTTPClient, "_get_session", return_value=session),
        patch("time.monotonic", side_effect=lambda: clock[0]),
        patch(
            "time.sleep",
            side_effect=lambda delay: clock.__setitem__(0, clock[0] + delay),
        ),
    ):
        HTTPClient.get("https://example.test")
    budgets = [call.kwargs["timeout"] for call in session.get.call_args_list]
    assert [budget.total for budget in budgets] == [45, 24]
    assert budgets[0].read_timeout <= 30
    assert budgets[1].read_timeout <= 24
    assert all(budget.connect_timeout <= 5 for budget in budgets)


def test_retry_after_cannot_extend_deadline(monkeypatch):
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "1")
    session = Mock()
    reply = response(429, {"Retry-After": "3600"})
    session.get.return_value = reply
    with (
        patch.object(HTTPClient, "_get_session", return_value=session),
        patch("time.sleep") as sleep,
    ):
        with pytest.raises(ToolDeadlineExceeded, match="Retry would exceed"):
            HTTPClient.get("https://example.test")
    session.get.assert_called_once()
    sleep.assert_not_called()
    reply.close.assert_called_once()


def test_exhausted_attempt_cannot_start_another_retry(monkeypatch):
    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "1")
    clock = [0.0]
    session = Mock()

    def get(*args, **kwargs):
        clock[0] = 2
        raise requests.Timeout("slow")

    session.get.side_effect = get
    with (
        patch.object(HTTPClient, "_get_session", return_value=session),
        patch("time.monotonic", side_effect=lambda: clock[0]),
        patch("time.sleep") as sleep,
    ):
        with pytest.raises(ToolDeadlineExceeded):
            HTTPClient.get("https://example.test")
    session.get.assert_called_once()
    sleep.assert_not_called()


def test_sessions_are_reused_within_a_thread_and_separate_between_threads():
    HTTPClient.close_session()
    barrier = threading.Barrier(2)

    def get_session():
        first = HTTPClient._get_session()
        barrier.wait(timeout=2)
        assert HTTPClient._get_session() is first
        return first

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(get_session) for _ in range(2)]
            first, second = [job.result(timeout=2) for job in jobs]
        assert first is not second
    finally:
        HTTPClient.close_session()
