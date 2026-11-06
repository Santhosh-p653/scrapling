import inspect

from app.tools.search import search_web
from app.tools.scrape import fetch_page_knowledge, fetch_stealth_knowledge, batch_knowledge_extract
from app.tools.github import ingest_github_repo, fetch_github_file, fetch_github_issues, search_github_code
from app.tools.api import fetch_openapi_spec, fetch_graphql_schema, call_rest_api
from app.tools.crawl import scrape_docs_site, scrape_sitemap
from app.tools.documents import fetch_pdf_content
from app.tools.context import build_context_bundle, summarize_for_context, detect_content_type


# Tools grouped by phase. (function, phase, category, example_usage)
_TOOL_REGISTRY = [
    # Phase 0 — Core Scraping
    (search_web, 0, "search", 'search_web(query="scrapling python", max_results=5)'),
    (fetch_page_knowledge, 0, "scrape", 'fetch_page_knowledge(url="https://example.com")'),
    (fetch_stealth_knowledge, 0, "scrape", 'fetch_stealth_knowledge(url="https://cf-protected.com")'),
    (batch_knowledge_extract, 0, "scrape", 'batch_knowledge_extract(urls=["https://a.com", "https://b.com"])'),
    # Phase 1 — Repo & API Ingestion
    (ingest_github_repo, 1, "github", 'ingest_github_repo(repo_url="owner/repo", max_files=20)'),
    (fetch_github_file, 1, "github", 'fetch_github_file(repo_url="owner/repo", file_path="README.md")'),
    (fetch_github_issues, 1, "github", 'fetch_github_issues(repo_url="owner/repo", state="open")'),
    (search_github_code, 1, "github", 'search_github_code(query="def main", language="python")'),
    (fetch_openapi_spec, 1, "api", 'fetch_openapi_spec(url="https://api.example.com/openapi.json")'),
    (fetch_graphql_schema, 1, "api", 'fetch_graphql_schema(url="https://api.example.com/graphql")'),
    # Phase 2 — Docs & Site Crawling
    (scrape_docs_site, 2, "crawl", 'scrape_docs_site(start_url="https://docs.example.com", max_pages=10)'),
    (scrape_sitemap, 2, "crawl", 'scrape_sitemap(sitemap_url="https://example.com/sitemap.xml")'),
    (fetch_pdf_content, 2, "documents", 'fetch_pdf_content(url="https://example.com/paper.pdf")'),
    # Phase 3 — Context Management
    (detect_content_type, 3, "context", 'detect_content_type(url="https://github.com/owner/repo")'),
    (summarize_for_context, 3, "context", 'summarize_for_context(content="<long text>", target_length=1500)'),
    (build_context_bundle, 3, "context", 'build_context_bundle(sources=["owner/repo", "python gil"], topic="concurrency")'),
    # Phase 4 — Live API & Tool Calling
    (call_rest_api, 4, "api", 'call_rest_api(url="https://api.example.com/users", method="POST", body={"name": "x"})'),
]


def _build_input_schema(func) -> dict:
    """Introspect a function signature into a simple JSON-schema-like input map."""
    sig = inspect.signature(func)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        annotation = param.annotation
        # Best-effort type name
        if annotation is inspect.Parameter.empty:
            type_name = "any"
        elif hasattr(annotation, "__name__"):
            type_name = annotation.__name__
        else:
            type_name = str(annotation).replace("typing.", "")

        entry = {"type": type_name}
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            entry["default"] = param.default

        properties[name] = entry

    return {"properties": properties, "required": required}


def _first_line(doc: str | None) -> str:
    if not doc:
        return ""
    for line in doc.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


# ---------------------------------------------------------------------------
# Tool: list_available_tools  (Phase 4)
# ---------------------------------------------------------------------------

def list_available_tools() -> dict:
    """
    Returns a structured, self-describing manifest of every tool exposed by this
    MCP server. Agents can call this to dynamically discover capabilities,
    input schemas, and example usage without out-of-band documentation.

    Returns:
      {
        server, tool_count,
        tools: [ { name, phase, category, description, input_schema, example } ]
      }
    """
    tools = []
    for func, phase, category, example in _TOOL_REGISTRY:
        tools.append({
            "name": func.__name__,
            "phase": phase,
            "category": category,
            "description": _first_line(func.__doc__),
            "input_schema": _build_input_schema(func),
            "example": example,
        })

    return {
        "server": "scrapling-knowledge-engine",
        "tool_count": len(tools),
        "tools": tools,
    }
