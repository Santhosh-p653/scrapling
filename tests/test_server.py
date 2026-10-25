"""
Tests for app/server.py.

Coverage targets:
  - MCP initialization and tool registration
  - Health-check route
  - Web search success and error handling
  - Standard Scrapling extraction
  - Stealth extraction
  - Batch extraction
  - Error handling and content truncation

External services are mocked; these tests do not require live web requests.
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

from starlette.requests import Request

import app.server as server


# ===========================================================================
# Helpers
# ===========================================================================

def make_page(
    title="Test Page",
    status=200,
    article="<article><h1>Hello</h1><p>Test content</p></article>",
):
    """Create a mock Scrapling page."""

    page = MagicMock()
    page.status = status

    def css_side_effect(selector):
        result = MagicMock()

        if selector == "title::text":
            result.get.return_value = title
        elif selector == "article":
            result.get.return_value = article
        elif selector == "main":
            result.get.return_value = None
        elif selector == "#content":
            result.get.return_value = "<div>Fallback content</div>"
        elif selector == "body":
            result.get.return_value = "<body>Fallback content</body>"
        else:
            result.get.return_value = None

        return result

    page.css.side_effect = css_side_effect
    return page


def make_request(path="/healthz"):
    """Create a minimal Starlette HTTP request."""

    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "http_version": "1.1",
        "root_path": "",
    })


# ===========================================================================
# MCP initialization
# ===========================================================================

class TestMCPInitialization:
    def test_mcp_instance_exists(self):
        assert server.mcp is not None

    def test_expected_tools_are_registered(self):
        assert callable(server.search_web)
        assert callable(server.fetch_page_knowledge)
        assert callable(server.fetch_stealth_knowledge)
        assert callable(server.batch_knowledge_extract)


# ===========================================================================
# Health check
# ===========================================================================

class TestHealthCheck:
    def test_health_check_returns_healthy_status(self):
        response = asyncio.run(
            server.health_check(make_request())
        )

        assert response.status_code == 200

        payload = json.loads(response.body)

        assert payload["status"] == "healthy"
        assert payload["engine"] == "scrapling"
        assert payload["service"] == "scrapling-knowledge-engine"
        assert "timestamp" in payload

    def test_health_check_timestamp_is_iso_formatted(self):
        from datetime import datetime

        response = asyncio.run(
            server.health_check(make_request())
        )

        payload = json.loads(response.body)

        timestamp = datetime.fromisoformat(
            payload["timestamp"].replace("Z", "+00:00")
        )

        assert timestamp.tzinfo is not None


# ===========================================================================
# Web search
# ===========================================================================

class TestSearchWeb:
    @patch("app.server.DDGS")
    def test_search_returns_formatted_results(self, mock_ddgs):
        mock_instance = MagicMock()
        mock_ddgs.return_value.__enter__.return_value = mock_instance

        mock_instance.text.return_value = [
            {
                "title": "Python Docs",
                "href": "https://docs.python.org/",
                "body": "Official Python documentation",
            }
        ]

        result = server.search_web("Python documentation")

        assert len(result) == 1
        assert result[0]["title"] == "Python Docs"
        assert result[0]["url"] == "https://docs.python.org/"
        assert result[0]["snippet"] == "Official Python documentation"

        mock_instance.text.assert_called_once_with(
            "Python documentation",
            max_results=5,
        )

    @patch("app.server.DDGS")
    def test_search_uses_requested_result_limit(self, mock_ddgs):
        mock_instance = MagicMock()
        mock_ddgs.return_value.__enter__.return_value = mock_instance
        mock_instance.text.return_value = []

        result = server.search_web("Scrapling", max_results=3)

        assert result == []

        mock_instance.text.assert_called_once_with(
            "Scrapling",
            max_results=3,
        )

    @patch("app.server.DDGS")
    def test_search_returns_error_when_provider_fails(self, mock_ddgs):
        mock_ddgs.side_effect = RuntimeError(
            "Search provider unavailable"
        )

        result = server.search_web("test")

        assert len(result) == 1
        assert "error" in result[0]
        assert "Search failed" in result[0]["error"]

    @patch("app.server.DDGS")
    def test_search_handles_text_method_error(self, mock_ddgs):
        mock_instance = MagicMock()
        mock_ddgs.return_value.__enter__.return_value = mock_instance

        mock_instance.text.side_effect = RuntimeError(
            "Request failed"
        )

        result = server.search_web("test")

        assert "error" in result[0]
        assert "Search failed" in result[0]["error"]


# ===========================================================================
# Standard Scrapling extraction
# ===========================================================================

class TestFetchPageKnowledge:
    @patch("app.server.Fetcher")
    def test_success_returns_page_knowledge(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.get.return_value = make_page()

        result = server.fetch_page_knowledge(
            "https://example.com"
        )

        assert result["title"] == "Test Page"
        assert result["url"] == "https://example.com"
        assert "content" in result
        assert result["char_count"] >= 0
        assert "error" not in result

        mock_fetcher_class.assert_called_once_with(
            auto_match=False
        )

        mock_fetcher.get.assert_called_once_with(
            "https://example.com",
            stealthy_headers=True,
        )

    @patch("app.server.Fetcher")
    def test_http_error_returns_error(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.get.return_value = make_page(status=403)

        result = server.fetch_page_knowledge(
            "https://example.com"
        )

        assert "error" in result
        assert "403" in result["error"]

    @patch("app.server.Fetcher")
    def test_none_page_returns_error(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.get.return_value = None

        result = server.fetch_page_knowledge(
            "https://example.com"
        )

        assert "error" in result
        assert "Unknown" in result["error"]

    @patch("app.server.Fetcher")
    def test_fetch_exception_returns_error(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher

        mock_fetcher.get.side_effect = RuntimeError(
            "Connection failed"
        )

        result = server.fetch_page_knowledge(
            "https://example.com"
        )

        assert "error" in result
        assert "Scrapling extraction error" in result["error"]

    @patch("app.server.Fetcher")
    def test_content_is_truncated(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher

        page = make_page(
            article=(
                "<article><p>"
                + ("A" * 1000)
                + "</p></article>"
            )
        )

        mock_fetcher.get.return_value = page

        result = server.fetch_page_knowledge(
            "https://example.com",
            max_length=100,
        )

        assert len(result["content"]) > 100
        assert (
            "[... Truncated to fit token budget"
            in result["content"]
        )

    @patch("app.server.Fetcher")
    def test_missing_title_uses_default(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher

        page = make_page()
        page.css.side_effect = None

        def css_without_title(selector):
            result = MagicMock()

            if selector == "title::text":
                result.get.return_value = None
            elif selector == "article":
                result.get.return_value = (
                    "<article><p>Content</p></article>"
                )
            else:
                result.get.return_value = None

            return result

        page.css.side_effect = css_without_title
        mock_fetcher.get.return_value = page

        result = server.fetch_page_knowledge(
            "https://example.com"
        )

        assert result["title"] == "No title"


# ===========================================================================
# Stealth extraction
# ===========================================================================

class TestFetchStealthKnowledge:
    @patch("app.server.StealthyFetcher.fetch")
    def test_success_returns_stealth_knowledge(self, mock_fetch):
        mock_fetch.return_value = make_page()

        result = server.fetch_stealth_knowledge(
            "https://example.com"
        )

        assert result["title"] == "Test Page"
        assert result["url"] == "https://example.com"
        assert result["mode"] == "stealth"
        assert "content" in result
        assert "error" not in result

        mock_fetch.assert_called_once_with(
            "https://example.com",
            headless=True,
            network_idle=True,
        )

    @patch("app.server.StealthyFetcher.fetch")
    def test_stealth_exception_returns_error(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError(
            "Browser launch failed"
        )

        result = server.fetch_stealth_knowledge(
            "https://example.com"
        )

        assert "error" in result
        assert "Stealth extraction error" in result["error"]

    @patch("app.server.StealthyFetcher.fetch")
    def test_stealth_content_is_truncated(self, mock_fetch):
        mock_fetch.return_value = make_page(
            article=(
                "<article><p>"
                + ("B" * 1000)
                + "</p></article>"
            )
        )

        result = server.fetch_stealth_knowledge(
            "https://example.com",
            max_length=100,
        )

        assert len(result["content"]) > 100
        assert "[... Truncated]" in result["content"]


# ===========================================================================
# Batch extraction
# ===========================================================================

class TestBatchKnowledgeExtract:
    @patch("app.server.Fetcher")
    def test_extracts_multiple_urls(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher

        mock_fetcher.get.side_effect = [
            make_page(title="Page One"),
            make_page(title="Page Two"),
        ]

        urls = [
            "https://example.com/one",
            "https://example.com/two",
        ]

        result = server.batch_knowledge_extract(urls)

        assert len(result) == 2
        assert result[0]["title"] == "Page One"
        assert result[1]["title"] == "Page Two"
        assert result[0]["url"] == urls[0]
        assert result[1]["url"] == urls[1]

    @patch("app.server.Fetcher")
    def test_limits_batch_to_five_urls(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher
        mock_fetcher.get.return_value = make_page()

        urls = [
            f"https://example.com/{i}"
            for i in range(8)
        ]

        result = server.batch_knowledge_extract(urls)

        assert len(result) == 5
        assert mock_fetcher.get.call_count == 5

    @patch("app.server.Fetcher")
    def test_records_error_for_failed_url(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher

        mock_fetcher.get.side_effect = [
            make_page(title="Good Page"),
            RuntimeError("Network failure"),
        ]

        urls = [
            "https://example.com/good",
            "https://example.com/bad",
        ]

        result = server.batch_knowledge_extract(urls)

        assert len(result) == 2
        assert result[0]["title"] == "Good Page"
        assert result[1]["url"] == urls[1]
        assert "error" in result[1]

    @patch("app.server.Fetcher")
    def test_empty_url_list_returns_empty_list(self, mock_fetcher_class):
        result = server.batch_knowledge_extract([])

        assert result == []
        mock_fetcher_class.return_value.get.assert_not_called()

    @patch("app.server.Fetcher")
    def test_truncates_summary_content(self, mock_fetcher_class):
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher

        mock_fetcher.get.return_value = make_page(
            article=(
                "<article><p>"
                + ("C" * 3000)
                + "</p></article>"
            )
        )

        result = server.batch_knowledge_extract([
            "https://example.com"
        ])

        assert len(result[0]["summary_content"]) <= 2000