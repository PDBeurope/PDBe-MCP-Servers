from html.parser import HTMLParser
from typing import Any, Literal

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


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
    Uses a singleton session for connection pooling and better performance.
    """

    _session: requests.Session | None = None

    @classmethod
    def _get_session(cls) -> requests.Session:
        """
        Get or create the singleton session with retry configuration.

        Returns:
            Configured requests.Session instance
        """
        if cls._session is None:
            cls._session = cls._create_session()
        return cls._session

    @classmethod
    def close_session(cls) -> None:
        """
        Close the singleton session and reset it.
        Useful for cleanup or when you need to refresh the session.
        """
        if cls._session is not None:
            cls._session.close()
            cls._session = None

    @classmethod
    def _create_session(
        cls, max_retries: int = 3, retry_delay: float = 1.0
    ) -> requests.Session:
        """
        Create a new session with retry configuration.

        Args:
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds

        Returns:
            Configured requests.Session instance
        """
        session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    @staticmethod
    def get(
        url: str,
        params: dict[str, Any] | None = None,
        response_type: Literal["json", "xml", "text"] = "json",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
    ) -> Any:
        """
        Make an HTTP GET request with retry logic using the singleton session.

        Args:
            url: The URL to request
            params: Query parameters
            response_type: Type of response to return (json, xml, or text)
            max_retries: Maximum number of retries (only used if session needs recreation)
            retry_delay: Delay between retries in seconds (only used if session needs recreation)
            timeout: Request timeout in seconds

        Returns:
            Parsed response based on response_type

        Raises:
            requests.HTTPError: If the request fails after retries
        """
        session = HTTPClient._get_session()

        # If custom retry parameters are provided, create a temporary session
        if max_retries != 3 or retry_delay != 1.0:
            session = HTTPClient._create_session(max_retries, retry_delay)

        response = session.get(url, params=params, timeout=timeout)
        response.raise_for_status()

        if response_type == "json":
            return response.json()
        elif response_type == "xml":
            return response.text
        else:  # text
            return response.text

    @staticmethod
    def post(
        url: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        response_type: Literal["json", "xml", "text"] = "json",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
    ) -> Any:
        """
        Make an HTTP POST request with retry logic using the singleton session.

        Args:
            url: The URL to request
            data: Form data to send
            json: JSON data to send
            response_type: Type of response to return (json, xml, or text)
            max_retries: Maximum number of retries (only used if session needs recreation)
            retry_delay: Delay between retries in seconds (only used if session needs recreation)
            timeout: Request timeout in seconds

        Returns:
            Parsed response based on response_type

        Raises:
            requests.HTTPError: If the request fails after retries
        """
        session = HTTPClient._get_session()

        # If custom retry parameters are provided, create a temporary session
        if max_retries != 3 or retry_delay != 1.0:
            session = HTTPClient._create_session(max_retries, retry_delay)

        response = session.post(url, data=data, json=json, timeout=timeout)
        response.raise_for_status()

        if response_type == "json":
            return response.json()
        elif response_type == "xml":
            return response.text
        else:  # text
            return response.text
