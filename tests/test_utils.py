"""Tests for utils module."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from pdbe_mcp_server.utils import HTMLStripper, HTTPClient


class TestHTMLStripper:
    """Tests for HTMLStripper class."""

    def test_strip_simple_tags(self) -> None:
        """Test stripping simple HTML tags."""
        html = "<p>Hello<b>World</b></p>"
        result = HTMLStripper.strip_tags(html)
        assert result == "Hello World"

    def test_strip_nested_tags(self) -> None:
        """Test stripping nested HTML tags."""
        html = "<div><p>Hello<span><strong>World</strong></span></p></div>"
        result = HTMLStripper.strip_tags(html)
        assert result == "Hello World"

    def test_strip_with_attributes(self) -> None:
        """Test stripping tags with attributes."""
        html = '<p class="test">Hello<a href="test.html">World</a></p>'
        result = HTMLStripper.strip_tags(html)
        assert result == "Hello World"

    def test_empty_string(self) -> None:
        """Test with empty string."""
        result = HTMLStripper.strip_tags("")
        assert result == ""

    def test_no_tags(self) -> None:
        """Test plain text without tags."""
        text = "Hello World"
        result = HTMLStripper.strip_tags(text)
        assert result == "Hello World"

    def test_multiple_spaces(self) -> None:
        """Test that multiple spaces are preserved as single space."""
        html = "<p>Hello</p>   <p>World</p>"
        result = HTMLStripper.strip_tags(html)
        # The HTMLParser will create space-separated output
        assert "Hello" in result and "World" in result


class TestHTTPClient:
    """Tests for HTTPClient class."""

    def test_get_json_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful JSON GET request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value"}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("requests.Session", return_value=mock_session):
            result = HTTPClient.get("https://example.com", response_type="json")
            assert result == {"key": "value"}
            mock_session.get.assert_called_once()

    def test_get_text_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful text GET request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "response text"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("requests.Session", return_value=mock_session):
            result = HTTPClient.get("https://example.com", response_type="text")
            assert result == "response text"

    def test_get_xml_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful XML GET request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<xml>data</xml>"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("requests.Session", return_value=mock_session):
            result = HTTPClient.get("https://example.com", response_type="xml")
            assert result == "<xml>data</xml>"

    def test_get_with_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test GET request with parameters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "data"}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        params = {"key1": "value1", "key2": "value2"}

        with patch("requests.Session", return_value=mock_session):
            result = HTTPClient.get("https://example.com", params=params)
            assert result == {"result": "data"}
            mock_session.get.assert_called_once_with(
                "https://example.com", params=params, timeout=30
            )

    def test_get_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test GET request with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError("Not Found")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("requests.Session", return_value=mock_session):
            with pytest.raises(requests.HTTPError):
                HTTPClient.get("https://example.com")

    def test_post_json_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful JSON POST request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "created"}

        mock_session = MagicMock()
        mock_session.post.return_value = mock_response

        json_data = {"field": "value"}

        with patch("requests.Session", return_value=mock_session):
            result = HTTPClient.post("https://example.com", json=json_data)
            assert result == {"status": "created"}
            mock_session.post.assert_called_once_with(
                "https://example.com", data=None, json=json_data, timeout=30
            )

    def test_post_form_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test POST request with form data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        mock_session = MagicMock()
        mock_session.post.return_value = mock_response

        form_data = {"field1": "value1", "field2": "value2"}

        with patch("requests.Session", return_value=mock_session):
            result = HTTPClient.post("https://example.com", data=form_data)
            assert result == {"status": "ok"}
            mock_session.post.assert_called_once_with(
                "https://example.com", data=form_data, json=None, timeout=30
            )

    def test_post_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test POST request with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "Internal Server Error"
        )

        mock_session = MagicMock()
        mock_session.post.return_value = mock_response

        with patch("requests.Session", return_value=mock_session):
            with pytest.raises(requests.HTTPError):
                HTTPClient.post("https://example.com")

    def test_custom_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test request with custom timeout."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("requests.Session", return_value=mock_session):
            HTTPClient.get("https://example.com", timeout=60)
            mock_session.get.assert_called_once_with(
                "https://example.com", params=None, timeout=60
            )

    def test_retry_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that retry strategy is properly configured."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("requests.Session", return_value=mock_session):
            HTTPClient.get("https://example.com", max_retries=5, retry_delay=2.0)
            # Verify that mount was called to set up adapters
            assert mock_session.mount.call_count == 2  # Once for http, once for https
