"""
Tests for app/tools/github.py

Coverage targets:
  - _parse_repo_url: full URL, shorthand, .git suffix, trailing slash, invalid
  - _detect_language: every mapped extension + plaintext fallback
  - _gh_headers: with and without token
  - ingest_github_repo: success, master-fallback, no matching files, tree API error,
                        missing 'tree' key, raw-file fetch error, with token
  - fetch_github_file: success, master-fallback, HTTP error, invalid URL
  - fetch_github_issues: success, PR skipping, comments fetched, comment fetch failure,
                         non-list response, HTTP error, invalid URL
  - search_github_code: success with preview, no items, HTTP error,
                        with repo URL filter, with language filter, raw fetch failure
"""
import pytest
from unittest.mock import patch, MagicMock, call
from requests.exceptions import HTTPError, ConnectionError as ReqConnectionError

from app.tools.github import (
    _parse_repo_url,
    _detect_language,
    _gh_headers,
    ingest_github_repo,
    fetch_github_file,
    fetch_github_issues,
    search_github_code,
)
from tests.conftest import make_response


# ===========================================================================
# _parse_repo_url
# ===========================================================================

class TestParseRepoUrl:
    def test_full_https_url(self):
        assert _parse_repo_url("https://github.com/owner/repo") == ("owner", "repo")

    def test_full_url_with_git_suffix(self):
        assert _parse_repo_url("https://github.com/owner/repo.git") == ("owner", "repo")

    def test_full_url_with_trailing_slash(self):
        assert _parse_repo_url("https://github.com/owner/repo/") == ("owner", "repo")

    def test_shorthand_owner_slash_repo(self):
        assert _parse_repo_url("owner/repo") == ("owner", "repo")

    def test_http_url(self):
        assert _parse_repo_url("http://github.com/owner/repo") == ("owner", "repo")

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            _parse_repo_url("not-a-valid-url")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            _parse_repo_url("")

    def test_single_segment_raises(self):
        with pytest.raises(ValueError):
            _parse_repo_url("just-one-segment")


# ===========================================================================
# _detect_language
# ===========================================================================

class TestDetectLanguage:
    @pytest.mark.parametrize("path,expected", [
        ("file.py",        "python"),
        ("file.ts",        "typescript"),
        ("file.tsx",       "typescript"),
        ("file.js",        "javascript"),
        ("file.jsx",       "javascript"),
        ("file.md",        "markdown"),
        ("file.json",      "json"),
        ("file.yaml",      "yaml"),
        ("file.yml",       "yaml"),
        ("file.html",      "html"),
        ("file.css",       "css"),
        ("file.sh",        "shell"),
        ("file.go",        "go"),
        ("file.rs",        "rust"),
        ("file.java",      "java"),
        ("file.rb",        "ruby"),
        ("file.cpp",       "cpp"),
        ("file.c",         "c"),
        ("file.cs",        "csharp"),
        ("file.tf",        "terraform"),
        ("file.unknown",   "plaintext"),
        ("Makefile",       "plaintext"),
        ("",               "plaintext"),
    ])
    def test_extension_mapping(self, path, expected):
        assert _detect_language(path) == expected


# ===========================================================================
# _gh_headers
# ===========================================================================

class TestGhHeaders:
    def test_without_token(self):
        h = _gh_headers(None)
        assert "Accept" in h
        assert "Authorization" not in h

    def test_with_token(self):
        h = _gh_headers("mytoken")
        assert h["Authorization"] == "Bearer mytoken"
        assert "Accept" in h


# ===========================================================================
# ingest_github_repo
# ===========================================================================

class TestIngestGithubRepo:
    @patch("app.tools.github.requests.get")
    def test_success_returns_file_list(self, mock_get, gh_tree_response, gh_raw_content_response):
        # First call → tree; subsequent calls → raw file content
        mock_get.side_effect = [
            gh_tree_response,
            gh_raw_content_response,  # README.md
            gh_raw_content_response,  # app/server.py
            gh_raw_content_response,  # app/tools/__init__.py
        ]
        result = ingest_github_repo("owner/repo", file_extensions=[".py", ".md"])
        # README.md and app/server.py and __init__.py all match
        assert isinstance(result, list)
        assert len(result) >= 1
        assert "error" not in result[0]
        assert result[0]["content"] == "print('hello world')"
        assert result[0]["char_count"] > 0

    @patch("app.tools.github.requests.get")
    def test_master_fallback_on_404(self, mock_get, gh_tree_response, gh_raw_content_response):
        not_found = make_response(status_code=404, json_data={"message": "Not Found"})
        not_found.raise_for_status.return_value = None  # 404 checked manually, not via raise_for_status
        mock_get.side_effect = [
            not_found,          # main → 404
            gh_tree_response,   # master → 200
            gh_raw_content_response,
            gh_raw_content_response,
            gh_raw_content_response,
        ]
        result = ingest_github_repo("https://github.com/owner/repo")
        assert isinstance(result, list)
        assert "error" not in result[0]

    @patch("app.tools.github.requests.get")
    def test_no_matching_files(self, mock_get):
        resp = make_response(json_data={"tree": [
            {"type": "blob", "path": "Makefile", "sha": "aaa"},
        ]})
        mock_get.return_value = resp
        result = ingest_github_repo("owner/repo", file_extensions=[".py"])
        assert len(result) == 1
        assert "error" in result[0]

    @patch("app.tools.github.requests.get")
    def test_tree_api_http_error(self, mock_get):
        mock_get.side_effect = ReqConnectionError("connection refused")
        result = ingest_github_repo("owner/repo")
        assert len(result) == 1
        assert "error" in result[0]
        assert "GitHub API error" in result[0]["error"]

    @patch("app.tools.github.requests.get")
    def test_missing_tree_key_in_response(self, mock_get):
        resp = make_response(json_data={"message": "Git Repository is empty."})
        mock_get.return_value = resp
        result = ingest_github_repo("owner/repo")
        assert "error" in result[0]
        assert "unexpected tree response" in result[0]["error"]

    @patch("app.tools.github.requests.get")
    def test_raw_file_fetch_error_recorded(self, mock_get, gh_tree_response):
        raw_err = make_response(status_code=500)
        mock_get.side_effect = [gh_tree_response, raw_err, raw_err, raw_err]
        result = ingest_github_repo("owner/repo", file_extensions=[".py", ".md"])
        # Should record error per file, not crash
        for item in result:
            assert "error" in item

    @patch("app.tools.github.requests.get")
    def test_invalid_repo_url(self, mock_get):
        result = ingest_github_repo("not-valid")
        assert "error" in result[0]
        mock_get.assert_not_called()

    @patch("app.tools.github.requests.get")
    def test_max_files_is_respected(self, mock_get):
        # Build a tree with 10 .py files
        tree = {"tree": [{"type": "blob", "path": f"f{i}.py", "sha": str(i)} for i in range(10)]}
        raw = make_response(text="code")
        mock_get.side_effect = [make_response(json_data=tree)] + [raw] * 3
        result = ingest_github_repo("owner/repo", max_files=3, file_extensions=[".py"])
        assert len(result) == 3

    @patch("app.tools.github.requests.get")
    def test_with_github_token(self, mock_get, gh_tree_response, gh_raw_content_response):
        mock_get.side_effect = [gh_tree_response, gh_raw_content_response,
                                gh_raw_content_response, gh_raw_content_response]
        ingest_github_repo("owner/repo", github_token="secret")
        first_call_headers = mock_get.call_args_list[0][1].get("headers", {})
        assert "Authorization" in first_call_headers


# ===========================================================================
# fetch_github_file
# ===========================================================================

class TestFetchGithubFile:
    @patch("app.tools.github.requests.get")
    def test_success(self, mock_get, gh_raw_content_response):
        mock_get.return_value = gh_raw_content_response
        result = fetch_github_file("owner/repo", "app/server.py")
        assert result["path"] == "app/server.py"
        assert result["content"] == "print('hello world')"
        assert result["language"] == "python"

    @patch("app.tools.github.requests.get")
    def test_master_fallback(self, mock_get, gh_raw_content_response):
        not_found = make_response(status_code=404)
        not_found.raise_for_status.return_value = None
        mock_get.side_effect = [not_found, gh_raw_content_response]
        result = fetch_github_file("owner/repo", "README.md", branch="main")
        assert "error" not in result
        assert result["language"] == "markdown"

    @patch("app.tools.github.requests.get")
    def test_http_error(self, mock_get):
        mock_get.side_effect = ReqConnectionError("timeout")
        result = fetch_github_file("owner/repo", "app/server.py")
        assert "error" in result
        assert "Failed to fetch file" in result["error"]

    def test_invalid_repo_url(self):
        result = fetch_github_file("bad-url", "file.py")
        assert "error" in result

    @patch("app.tools.github.requests.get")
    def test_typescript_language_detected(self, mock_get):
        mock_get.return_value = make_response(text="const x = 1;")
        result = fetch_github_file("owner/repo", "src/index.ts")
        assert result["language"] == "typescript"

    @patch("app.tools.github.requests.get")
    def test_with_token_sends_auth_header(self, mock_get, gh_raw_content_response):
        mock_get.return_value = gh_raw_content_response
        fetch_github_file("owner/repo", "file.py", github_token="tok123")
        headers_sent = mock_get.call_args[1].get("headers", {})
        assert headers_sent.get("Authorization") == "Bearer tok123"


# ===========================================================================
# fetch_github_issues
# ===========================================================================

class TestFetchGithubIssues:
    @patch("app.tools.github.requests.get")
    def test_success_and_pr_skipped(self, mock_get, gh_issues_response):
        mock_get.return_value = gh_issues_response
        result = fetch_github_issues("owner/repo")
        # 2 items in fixture but the PR should be skipped
        assert len(result) == 1
        assert result[0]["number"] == 1
        assert result[0]["title"] == "Bug: something broken"
        assert result[0]["labels"] == ["bug"]

    @patch("app.tools.github.requests.get")
    def test_comments_are_fetched(self, mock_get, gh_issues_with_comments_response, gh_comments_response):
        mock_get.side_effect = [gh_issues_with_comments_response, gh_comments_response]
        result = fetch_github_issues("owner/repo")
        assert len(result) == 1
        assert len(result[0]["comments"]) == 1
        assert result[0]["comments"][0]["author"] == "dave"
        assert result[0]["comments"][0]["body"] == "This is a comment."

    @patch("app.tools.github.requests.get")
    def test_comment_fetch_failure_is_silent(self, mock_get, gh_issues_with_comments_response):
        # Comments request raises — should not propagate
        mock_get.side_effect = [
            gh_issues_with_comments_response,
            ReqConnectionError("timeout"),
        ]
        result = fetch_github_issues("owner/repo")
        assert len(result) == 1
        assert result[0]["comments"] == []

    @patch("app.tools.github.requests.get")
    def test_non_list_response_returns_error(self, mock_get):
        mock_get.return_value = make_response(json_data={"message": "Not Found"})
        result = fetch_github_issues("owner/repo")
        assert "error" in result[0]

    @patch("app.tools.github.requests.get")
    def test_http_error_returns_error(self, mock_get):
        mock_get.side_effect = ReqConnectionError("refused")
        result = fetch_github_issues("owner/repo")
        assert "error" in result[0]
        assert "GitHub API error" in result[0]["error"]

    def test_invalid_repo_url_returns_error(self):
        result = fetch_github_issues("not-valid")
        assert "error" in result[0]

    @patch("app.tools.github.requests.get")
    def test_state_param_passed(self, mock_get):
        mock_get.return_value = make_response(json_data=[])
        fetch_github_issues("owner/repo", state="closed")
        params = mock_get.call_args[1]["params"]
        assert params["state"] == "closed"

    @patch("app.tools.github.requests.get")
    def test_max_issues_limits_results(self, mock_get):
        issues = [
            {
                "number": i, "title": f"Issue {i}", "state": "open",
                "user": {"login": "u"}, "labels": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "body": "", "comments": 0,
                "comments_url": "https://api.github.com/repos/o/r/issues/1/comments",
                "html_url": f"https://github.com/o/r/issues/{i}",
            }
            for i in range(1, 6)
        ]
        mock_get.return_value = make_response(json_data=issues)
        result = fetch_github_issues("owner/repo", max_issues=2)
        assert len(result) == 2


# ===========================================================================
# search_github_code
# ===========================================================================

class TestSearchGithubCode:
    @patch("app.tools.github.requests.get")
    def test_success_with_content_preview(self, mock_get, gh_code_search_response):
        raw_preview = make_response(text="def main(): pass")
        mock_get.side_effect = [gh_code_search_response, raw_preview]
        result = search_github_code("def main")
        assert len(result) == 1
        assert result[0]["repo"] == "owner/repo"
        assert result[0]["path"] == "app/server.py"
        assert result[0]["language"] == "python"
        assert result[0]["content_preview"] == "def main(): pass"

    @patch("app.tools.github.requests.get")
    def test_no_items_returns_empty_list(self, mock_get):
        mock_get.return_value = make_response(json_data={"items": []})
        result = search_github_code("nothing")
        assert result == []

    @patch("app.tools.github.requests.get")
    def test_http_error_returns_error(self, mock_get):
        mock_get.side_effect = ReqConnectionError("refused")
        result = search_github_code("query")
        assert "error" in result[0]
        assert "code search error" in result[0]["error"]

    @patch("app.tools.github.requests.get")
    def test_raw_preview_failure_is_silent(self, mock_get, gh_code_search_response):
        mock_get.side_effect = [gh_code_search_response, ReqConnectionError("timeout")]
        result = search_github_code("def main")
        assert len(result) == 1
        assert result[0]["content_preview"] is None

    @patch("app.tools.github.requests.get")
    def test_repo_filter_appended_to_query(self, mock_get, gh_code_search_response):
        mock_get.side_effect = [gh_code_search_response, make_response(text="")]
        search_github_code("query", repo="owner/repo")
        params = mock_get.call_args_list[0][1]["params"]
        assert "repo:owner/repo" in params["q"]

    @patch("app.tools.github.requests.get")
    def test_language_filter_appended_to_query(self, mock_get, gh_code_search_response):
        mock_get.side_effect = [gh_code_search_response, make_response(text="")]
        search_github_code("query", language="python")
        params = mock_get.call_args_list[0][1]["params"]
        assert "language:python" in params["q"]

    @patch("app.tools.github.requests.get")
    def test_max_results_limits_output(self, mock_get):
        items = [
            {
                "repository": {"full_name": f"owner/repo{i}"},
                "path": f"file{i}.py",
                "html_url": f"https://github.com/owner/repo{i}/blob/main/file{i}.py",
            }
            for i in range(5)
        ]
        mock_get.side_effect = [make_response(json_data={"items": items})] + [make_response(text="")] * 3
        result = search_github_code("query", max_results=3)
        assert len(result) == 3

    @patch("app.tools.github.requests.get")
    def test_repo_filter_with_full_url(self, mock_get, gh_code_search_response):
        mock_get.side_effect = [gh_code_search_response, make_response(text="")]
        search_github_code("query", repo="https://github.com/owner/repo")
        params = mock_get.call_args_list[0][1]["params"]
        assert "repo:owner/repo" in params["q"]
