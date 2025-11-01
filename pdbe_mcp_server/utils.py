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
    """

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
        Make an HTTP GET request with retry logic.

        Args:
            url: The URL to request
            params: Query parameters
            response_type: Type of response to return (json, xml, or text)
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
            timeout: Request timeout in seconds

        Returns:
            Parsed response based on response_type

        Raises:
            requests.HTTPError: If the request fails after retries
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
        Make an HTTP POST request with retry logic.

        Args:
            url: The URL to request
            data: Form data to send
            json: JSON data to send
            response_type: Type of response to return (json, xml, or text)
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
            timeout: Request timeout in seconds

        Returns:
            Parsed response based on response_type

        Raises:
            requests.HTTPError: If the request fails after retries
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

        response = session.post(url, data=data, json=json, timeout=timeout)
        response.raise_for_status()

        if response_type == "json":
            return response.json()
        elif response_type == "xml":
            return response.text
        else:  # text
            return response.text
