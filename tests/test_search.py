"""
Tests for app/tools/search.py

Coverage targets:
  - search_web: success with results, empty results, DDGS exception,
                max_results param respected, result shape validated
"""
import pytest
from unittest.mock import patch, MagicMock

from app.tools.search import search_web


# ===========================================================================
# search_web
# ===========================================================================

class TestSearchWeb:
    @patch("app.tools.search.DDGS")
    def test_success_returns_list_of_dicts(self, mock_ddgs_cls):
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.return_value = [
            {"title": "Result 1", "href": "https://example.com/1", "body": "Snippet 1"},
            {"title": "Result 2", "href": "https://example.com/2", "body": "Snippet 2"},
        ]
        result = search_web("python asyncio")
        assert isinstance(result, list)
        assert len(result) == 2

    @patch("app.tools.search.DDGS")
    def test_result_shape(self, mock_ddgs_cls):
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.return_value = [
            {"title": "My Title", "href": "https://example.com", "body": "My snippet"},
        ]
        result = search_web("anything")
        assert result[0]["title"] == "My Title"
        assert result[0]["url"] == "https://example.com"
        assert result[0]["snippet"] == "My snippet"

    @patch("app.tools.search.DDGS")
    def test_empty_results(self, mock_ddgs_cls):
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.return_value = []
        result = search_web("something obscure")
        assert result == []

    @patch("app.tools.search.DDGS")
    def test_ddgs_exception_returns_error(self, mock_ddgs_cls):
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.side_effect = Exception("rate limited")
        result = search_web("query")
        assert len(result) == 1
        assert "error" in result[0]
        assert "rate limited" in result[0]["error"]

    @patch("app.tools.search.DDGS")
    def test_max_results_passed_to_ddgs(self, mock_ddgs_cls):
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.return_value = []
        search_web("query", max_results=10)
        mock_ddgs.text.assert_called_once_with("query", max_results=10)

    @patch("app.tools.search.DDGS")
    def test_default_max_results_is_5(self, mock_ddgs_cls):
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.return_value = []
        search_web("query")
        mock_ddgs.text.assert_called_once_with("query", max_results=5)

    @patch("app.tools.search.DDGS")
    def test_missing_fields_handled_gracefully(self, mock_ddgs_cls):
        """DDGS sometimes returns partial dicts — missing keys should come back as None."""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.return_value = [{"title": "Only title"}]  # no href, no body
        result = search_web("query")
        assert result[0]["url"] is None
        assert result[0]["snippet"] is None

    @patch("app.tools.search.DDGS")
    def test_context_manager_enter_exception(self, mock_ddgs_cls):
        mock_ddgs_cls.return_value.__enter__.side_effect = Exception("init failed")
        result = search_web("query")
        assert "error" in result[0]
