"""
Root conftest.py — stubs out heavy/unavailable dependencies before pytest
collects any test modules. This lets the test suite run in a minimal
environment (CI, dev machine) without requiring scrapling, markdownify,
or duckduckgo_search to be installed.

The actual behaviour of these libraries is exercised through mocks inside
the individual test files; we only need the module-level imports to resolve.
"""
import sys
from unittest.mock import MagicMock


def _stub(name: str) -> MagicMock:
    """Register a MagicMock under *name* in sys.modules and return it."""
    mock = MagicMock()
    sys.modules[name] = mock
    return mock


# Only stub if the real package is absent — don't shadow a real installation.
if "scrapling" not in sys.modules:
    scrapling_mock = _stub("scrapling")
    fetchers_mock = _stub("scrapling.fetchers")
    # Fetcher and StealthyFetcher must be accessible as attributes
    fetchers_mock.Fetcher = MagicMock()
    fetchers_mock.StealthyFetcher = MagicMock()
    scrapling_mock.fetchers = fetchers_mock

if "markdownify" not in sys.modules:
    markdownify_mock = _stub("markdownify")
    # markdownify is called as:  from markdownify import markdownify as md
    markdownify_mock.markdownify = MagicMock(return_value="")

if "duckduckgo_search" not in sys.modules:
    ddgs_mock = _stub("duckduckgo_search")
    ddgs_mock.DDGS = MagicMock()
