import math
import threading
import time
from html.parser import HTMLParser
from typing import Any, Literal

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InvalidHeader
from urllib3.util.retry import Retry
from urllib3.util.timeout import Timeout

from pdbe_mcp_server.execution import (
    ToolDeadlineExceeded,
    remaining_seconds,
    request_budget,
)


class HTMLStripper:
    """
    A static class that strips HTML tags from a string.
    """

    @staticmethod
    def strip_tags(html: str) -> str:
        class _HTMLParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.fed: list[str] = []

            def handle_data(self, data: str) -> None:
                self.fed.append(data)

            def get_data(self) -> str:
                return " ".join(self.fed)

        parser = _HTMLParser()
        parser.feed(html)
        return parser.get_data()


class HTTPClient:
    """
    HTTP client with retry logic and support for multiple response types.
    Pools connections per thread; retries share one overall request budget.
    """

    _local = threading.local()
    _sessions: set[requests.Session] = set()
    _lock = threading.Lock()
    _generation = 0

    @classmethod
    def _get_session(cls) -> requests.Session:
        """
        Get a connection pool owned by the current thread.

        Returns:
            Configured requests.Session instance
        """
        with cls._lock:
            if getattr(cls._local, "generation", None) != cls._generation:
                cls._local.session = cls._create_session()
                cls._local.generation = cls._generation
                cls._sessions.add(cls._local.session)
            return cls._local.session

    @classmethod
    def close_session(cls) -> None:
        """
        Close all thread pools after requests have drained at shutdown.
        """
        with cls._lock:
            for session in cls._sessions:
                session.close()
            cls._sessions.clear()
            cls._generation += 1

    @classmethod
    def _create_session(cls) -> requests.Session:
        """Disable hidden adapter retries; _request owns the complete policy."""
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    @staticmethod
    def _request(
        method: str,
        url: str,
        response_type: Literal["json", "xml", "text"],
        max_retries: int,
        retry_delay: float,
        timeout: float,
        **kwargs: Any,
    ) -> Any:
        if max_retries < 0 or not math.isfinite(retry_delay) or retry_delay < 0:
            raise ValueError("Retry count and delay must be nonnegative")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("HTTP timeout must be positive and finite")
        # A direct synchronous call gets a budget too. Calls from async tools
        # inherit the budget set before entering the worker queue.
        with request_budget():
            session = HTTPClient._get_session()
            for attempt in range(max_retries + 1):
                remaining = remaining_seconds()
                response = None
                delay = retry_delay * (2**attempt)
                try:
                    response = getattr(session, method)(
                        url,
                        timeout=Timeout(
                            total=remaining,
                            connect=min(5.0, timeout, remaining),
                            read=min(timeout, remaining),
                        ),
                        **kwargs,
                    )
                    response.raise_for_status()
                    result = (
                        response.json() if response_type == "json" else response.text
                    )
                    remaining_seconds()
                    return result
                except (
                    requests.ConnectionError,
                    requests.Timeout,
                    requests.HTTPError,
                ) as error:
                    if (
                        isinstance(error, ToolDeadlineExceeded)
                        or attempt == max_retries
                    ):
                        raise
                    if isinstance(error, requests.HTTPError):
                        if response is None or response.status_code not in {
                            429,
                            500,
                            502,
                            503,
                            504,
                        }:
                            raise
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = max(
                                    delay, Retry().parse_retry_after(retry_after)
                                )
                            except InvalidHeader:
                                pass
                finally:
                    if response is not None:
                        response.close()
                if delay >= remaining_seconds():
                    raise ToolDeadlineExceeded("Retry would exceed the tool deadline")
                time.sleep(delay)
        raise RuntimeError("HTTP request did not complete")

    @staticmethod
    def get(
        url: str,
        params: dict[str, Any] | None = None,
        response_type: Literal["json", "xml", "text"] = "json",
        max_retries: int = 2,
        retry_delay: float = 1.0,
        timeout: float = 30,
    ) -> Any:
        """
        Make an HTTP GET request with deadline-aware retries.

        Args:
            url: The URL to request
            params: Query parameters
            response_type: Type of response to return (json, xml, or text)
            max_retries: Retries after the initial attempt
            retry_delay: Initial exponential backoff in seconds
            timeout: Request timeout in seconds

        Returns:
            Parsed response based on response_type

        Raises:
            requests.HTTPError: If the request fails after retries
        """
        return HTTPClient._request(
            "get", url, response_type, max_retries, retry_delay, timeout, params=params
        )

    @staticmethod
    def post(
        url: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        response_type: Literal["json", "xml", "text"] = "json",
        max_retries: int = 0,
        retry_delay: float = 1.0,
        timeout: float = 30,
    ) -> Any:
        """
        Make an HTTP POST request. Retries require an explicit opt-in.

        Args:
            url: The URL to request
            data: Form data to send
            json: JSON data to send
            response_type: Type of response to return (json, xml, or text)
            max_retries: Retries after the initial attempt (default zero for POST)
            retry_delay: Initial exponential backoff in seconds
            timeout: Request timeout in seconds

        Returns:
            Parsed response based on response_type

        Raises:
            requests.HTTPError: If the request fails after retries
        """
        return HTTPClient._request(
            "post",
            url,
            response_type,
            max_retries,
            retry_delay,
            timeout,
            data=data,
            json=json,
        )
