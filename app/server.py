import datetime
from fastmcp import FastMCP
from starlette.responses import JSONResponse

from app.tools.search import search_web
from app.tools.scrape import fetch_page_knowledge, fetch_stealth_knowledge, batch_knowledge_extract
from app.tools.github import ingest_github_repo, fetch_github_file, fetch_github_issues, search_github_code
from app.tools.api import fetch_openapi_spec, fetch_graphql_schema, call_rest_api
from app.tools.crawl import scrape_docs_site, scrape_sitemap
from app.tools.documents import fetch_pdf_content
from app.tools.context import build_context_bundle, summarize_for_context, detect_content_type
from app.tools.manifest import list_available_tools

mcp = FastMCP("scrapling-knowledge-engine")

# -------------------------------------------------------------
# Health Check Route (Lightsail / load balancers)
# -------------------------------------------------------------
@mcp.custom_route("/healthz", methods=["GET"])
async def health_check(request):
    return JSONResponse({
        "status": "healthy",
        "engine": "scrapling",
        "service": "scrapling-knowledge-engine",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })

# -------------------------------------------------------------
# Phase 0 — Core Scraping
# -------------------------------------------------------------
mcp.tool()(search_web)
mcp.tool()(fetch_page_knowledge)
mcp.tool()(fetch_stealth_knowledge)
mcp.tool()(batch_knowledge_extract)

# -------------------------------------------------------------
# Phase 1 — Repo & API Ingestion
# -------------------------------------------------------------
mcp.tool()(ingest_github_repo)
mcp.tool()(fetch_github_file)
mcp.tool()(fetch_github_issues)
mcp.tool()(search_github_code)
mcp.tool()(fetch_openapi_spec)
mcp.tool()(fetch_graphql_schema)

# -------------------------------------------------------------
# Phase 2 — Docs & Site Crawling
# -------------------------------------------------------------
mcp.tool()(scrape_docs_site)
mcp.tool()(scrape_sitemap)
mcp.tool()(fetch_pdf_content)

# -------------------------------------------------------------
# Phase 3 — Context Management
# -------------------------------------------------------------
mcp.tool()(detect_content_type)
mcp.tool()(summarize_for_context)
mcp.tool()(build_context_bundle)

# -------------------------------------------------------------
# Phase 4 — Live API & Tool Calling
# -------------------------------------------------------------
mcp.tool()(call_rest_api)
mcp.tool()(list_available_tools)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
