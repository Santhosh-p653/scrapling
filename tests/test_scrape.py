"""
Tests for app/tools/scrape.py

Coverage targets:
  - fetch_page_knowledge: success with article/main/#content/body selectors,
                          HTTP error status, truncation at max_length,
                          exception from fetcher, no content extracted
  - fetch_stealth_knowledge: success, truncation, exception
  - batch_knowledge_extract: success, partial failure per URL, max 5 URLs enforced
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from app.tools.scrape import (
    fetch_page_knowledge,
    fetch_stealth_knowledge,
    batch_knowledge_extract,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_page(
    title: str = "Test Page",
    status: int = 200,
    article: str | None = None,
    main: str | None = None,
    content_id: str | None = None,
    body: str | None = None,
):
    """
    Build a mock Scrapling page object.
    css() returns a mock whose .get() yields the provided HTML string or None.
    """
    page = MagicMock()
    page.status = status

    def css_side_effect(selector):
        result = MagicMock()
        mapping = {
            "title::text": title,
            "article":     article,
            "main":        main,
            "#content":    content_id,
            "body":        body,
        }
        result.get.return_value = mapping.get(selector)
        return result

    page.css.side_effect = css_side_effect
    return page


# ===========================================================================
# fetch_page_knowledge
# ===========================================================================

class TestFetchPageKnowledge:
    @patch("app.tools.scrape.Fetcher")
    def test_success_with_article_tag(self, mock_fetcher_cls):
        page = make_page(article="<article><p>Hello world</p></article>")
        mock_fetcher_cls.return_value.get.return_value = page
        result = fetch_page_knowledge("https://example.com")
        assert "error" not in result
        assert result["title"] == "Test Page"
        assert result["url"] == "https://example.com"
        assert "Hello world" in result["content"]
        assert result["char_count"] > 0

    @patch("app.tools.scrape.Fetcher")
    def test_success_with_main_tag_fallback(self, mock_fetcher_cls):
        page = make_page(main="<main><p>Main content</p></main>")
        mock_fetcher_cls.return_value.get.return_value = page
        result = fetch_page_knowledge("https://example.com")
        assert "error" not in result
        assert "Main content" in result["content"]

    @patch("app.tools.scrape.Fetcher")
    def test_success_with_content_id_fallback(self, mock_fetcher_cls):
        page = make_page(content_id="<div id='content'><p>Content div</p></div>")
        mock_fetcher_cls.return_value.get.return_value = page
        result = fetch_page_knowledge("https://example.com")
        assert "error" not in result

    @patch("app.tools.scrape.Fetcher")
    def test_success_with_body_fallback(self, mock_fetcher_cls):
        page = make_page(body="<body><p>Body content</p></body>")
        mock_fetcher_cls.return_value.get.return_value = page
        result = fetch_page_knowledge("https://example.com")
        assert "error" not in result
        assert "Body content" in result["content"]

    @patch("app.tools.scrape.Fetcher")
    def test_http_error_status_returns_error(self, mock_fetcher_cls):
        page = make_page(status=404)
        mock_fetcher_cls.return_value.get.return_value = page
        result = fetch_page_knowledge("https://example.com")
        assert "error" in result
        assert "404" in result["error"]

    @patch("app.tools.scrape.Fetcher")
    def test_none_page_returns_error(self, mock_fetcher_cls):
        mock_fetcher_cls.return_value.get.return_value = None
        result = fetch_page_knowledge("https://example.com")
        assert "error" in result

    @patch("app.tools.scrape.Fetcher")
    def test_content_truncated_at_max_length(self, mock_fetcher_cls):
        long_text = "A" * 10000
        page = make_page(body=f"<body><p>{long_text}</p></body>")
        mock_fetcher_cls.return_value.get.return_value = page
        result = fetch_page_knowledge("https://example.com", max_length=500)
        assert len(result["content"]) <= 600  # truncation marker adds ~80 chars
        assert "Truncated" in result["content"]

    @patch("app.tools.scrape.Fetcher")
    def test_no_content_fallback_message(self, mock_fetcher_cls):
        # All selectors return None → empty string → no text
        page = make_page(title="Empty Page")
        # Override so body returns empty string
        def css_side_effect(selector):
            r = MagicMock()
            r.get.return_value = "" if selector != "title::text" else "Empty Page"
            return r
        page.css.side_effect = css_side_effect
        mock_fetcher_cls.return_value.get.return_value = page
        result = fetch_page_knowledge("https://example.com")
        assert result["content"] == "No text could be extracted."

    @patch("app.tools.scrape.Fetcher")
    def test_fetcher_exception_returns_error(self, mock_fetcher_cls):
        mock_fetcher_cls.return_value.get.side_effect = Exception("network error")
        result = fetch_page_knowledge("https://example.com")
        assert "error" in result
        assert "extraction error" in result["error"]

    @patch("app.tools.scrape.Fetcher")
    def test_no_title_defaults_to_no_title(self, mock_fetcher_cls):
        page = make_page(title=None, body="<body><p>content</p></body>")
        mock_fetcher_cls.return_value.get.return_value = page
        result = fetch_page_knowledge("https://example.com")
        assert result["title"] == "No title"


# ===========================================================================
# fetch_stealth_knowledge
# ===========================================================================

class TestFetchStealthKnowledge:
    @patch("app.tools.scrape.StealthyFetcher")
    def test_success(self, mock_stealthy_cls):
        page = make_page(article="<article><p>Stealth content</p></article>")
        mock_stealthy_cls.fetch.return_value = page
        result = fetch_stealth_knowledge("https://example.com")
        assert "error" not in result
        assert result["mode"] == "stealth"
        assert "Stealth content" in result["content"]
        assert result["url"] == "https://example.com"

    @patch("app.tools.scrape.StealthyFetcher")
    def test_success_with_main_fallback(self, mock_stealthy_cls):
        page = make_page(main="<main><p>Main stealth</p></main>")
        mock_stealthy_cls.fetch.return_value = page
        result = fetch_stealth_knowledge("https://example.com")
        assert "error" not in result

    @patch("app.tools.scrape.StealthyFetcher")
    def test_truncation(self, mock_stealthy_cls):
        long_text = "B" * 8000
        page = make_page(body=f"<body><p>{long_text}</p></body>")
        mock_stealthy_cls.fetch.return_value = page
        result = fetch_stealth_knowledge("https://example.com", max_length=500)
        assert "Truncated" in result["content"]

    @patch("app.tools.scrape.StealthyFetcher")
    def test_exception_returns_error(self, mock_stealthy_cls):
        mock_stealthy_cls.fetch.side_effect = Exception("browser crash")
        result = fetch_stealth_knowledge("https://example.com")
        assert "error" in result
        assert "Stealth extraction error" in result["error"]

    @patch("app.tools.scrape.StealthyFetcher")
    def test_no_content_returns_fallback_message(self, mock_stealthy_cls):
        def css_side_effect(selector):
            r = MagicMock()
            r.get.return_value = "" if selector != "title::text" else "Title"
            return r
        page = MagicMock()
        page.css.side_effect = css_side_effect
        mock_stealthy_cls.fetch.return_value = page
        result = fetch_stealth_knowledge("https://example.com")
        assert result["content"] == "No text could be extracted."


# ===========================================================================
# batch_knowledge_extract
# ===========================================================================

class TestBatchKnowledgeExtract:
    @patch("app.tools.scrape.Fetcher")
    def test_success_all_urls(self, mock_fetcher_cls):
        page = make_page(article="<article><p>Content</p></article>")
        mock_fetcher_cls.return_value.get.return_value = page
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        result = batch_knowledge_extract(urls)
        assert len(result) == 3
        for item in result:
            assert "error" not in item
            assert "url" in item
            assert "title" in item
            assert "summary_content" in item

    @patch("app.tools.scrape.Fetcher")
    def test_max_5_urls_enforced(self, mock_fetcher_cls):
        page = make_page(body="<body><p>x</p></body>")
        mock_fetcher_cls.return_value.get.return_value = page
        urls = [f"https://example.com/{i}" for i in range(10)]
        result = batch_knowledge_extract(urls)
        assert len(result) == 5

    @patch("app.tools.scrape.Fetcher")
    def test_partial_failure_recorded(self, mock_fetcher_cls):
        page = make_page(body="<body><p>OK</p></body>")
        mock_fetcher_cls.return_value.get.side_effect = [
            page,
            Exception("timeout"),
            page,
        ]
        result = batch_knowledge_extract(["https://a.com", "https://b.com", "https://c.com"])
        assert len(result) == 3
        assert "error" not in result[0]
        assert "error" in result[1]
        assert result[1]["url"] == "https://b.com"
        assert "error" not in result[2]

    @patch("app.tools.scrape.Fetcher")
    def test_empty_url_list_returns_empty(self, mock_fetcher_cls):
        result = batch_knowledge_extract([])
        assert result == []
        mock_fetcher_cls.return_value.get.assert_not_called()

    @patch("app.tools.scrape.Fetcher")
    def test_summary_content_truncated_to_2000(self, mock_fetcher_cls):
        long_content = "X" * 5000
        page = make_page(body=f"<body><p>{long_content}</p></body>")
        mock_fetcher_cls.return_value.get.return_value = page
        result = batch_knowledge_extract(["https://example.com"])
        assert len(result[0]["summary_content"]) <= 2000

    @patch("app.tools.scrape.Fetcher")
    def test_no_title_defaults_correctly(self, mock_fetcher_cls):
        page = make_page(title=None, body="<body><p>content</p></body>")
        mock_fetcher_cls.return_value.get.return_value = page
        result = batch_knowledge_extract(["https://example.com"])
        assert result[0]["title"] == "No title"
