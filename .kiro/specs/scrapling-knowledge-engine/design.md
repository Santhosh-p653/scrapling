# Design — Scrapling Knowledge Engine

## Overview

A FastMCP server exposing knowledge-ingestion tools over `streamable-http`
(port 8080). Each tool is a plain Python function registered with
`mcp.tool()`; the function docstring is the agent-facing contract. Tools are
grouped by concern into modules under `app/tools/` and registered in
`app/server.py` in phase blocks.

## Architecture

```
AI client (IDE / agent / RAG)
        │  MCP over streamable-http :8080
        ▼
   app/server.py  ──  FastMCP("scrapling-knowledge-engine")
        │  registers tools + GET /healthz
        ▼
   app/tools/*.py  ──  stateless tool functions
        │
        ▼
 External sources: web, GitHub API, OpenAPI/GraphQL, sitemaps, PDFs, REST APIs
```

The server is stateless. No database, no embedding, no persistence — each tool
call fetches, normalizes, and returns. This keeps the server a reusable
capability that any client can layer storage/retrieval on top of.

## Components

### `server.py`

- Instantiates `FastMCP("scrapling-knowledge-engine")`.
- Defines `GET /healthz` via `@mcp.custom_route` returning status + UTC timestamp.
- Registers each tool with `mcp.tool()(fn)` under a phase comment block.
- `__main__` runs `mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)`.

### `tools/search.py`
- `search_web` — DuckDuckGo text search via `duckduckgo_search.DDGS`.

### `tools/scrape.py`
- `fetch_page_knowledge` — fast HTTP via Scrapling `Fetcher`, HTML→Markdown.
- `fetch_stealth_knowledge` — `StealthyFetcher` headless browser for bot-protected sites.
- `batch_knowledge_extract` — up to 5 URLs in one call.
- Shared pattern: selector fallback `article → main → #content → body`, then
  `markdownify` stripping noise tags, then length budget.

### `tools/github.py`
- `ingest_github_repo`, `fetch_github_file`, `fetch_github_issues`,
  `search_github_code`.
- Helpers: `_parse_repo_url` (URL/shorthand → owner/repo), `_gh_headers`
  (optional bearer token), `_detect_language` (extension → language).
- `main → master` fallback on 404; PRs filtered out of issues; comments
  best-effort.

### `tools/api.py`
- `fetch_openapi_spec` — JSON/YAML parse → endpoint summary (handles OpenAPI 3.x
  `servers` and Swagger 2.x `host`/`basePath`/`schemes`).
- `fetch_graphql_schema` — introspection query + `_unwrap_type` for readable
  type signatures (`[String!]!`).
- `call_rest_api` — generic caller; method allowlist; JSON body only for verbs
  that carry a payload; decodes JSON or falls back to text.

### `tools/crawl.py`
- `scrape_docs_site` — BFS internal-link crawl, same-domain bound, `max_pages`.
- `scrape_sitemap` — parses `sitemap.xml` incl. index files, batch-fetches.

### `tools/documents.py`
- `fetch_pdf_content` — downloads + extracts text via `pypdf`, handles encryption.

### `tools/context.py`
- `detect_content_type` — classify URL → suggested tool + confidence.
- `summarize_for_context` — compress to char budget, keep headings/code.
- `build_context_bundle` — multi-source ingest → chunk → rank by topic → one block.

### `tools/manifest.py`
- `list_available_tools` — self-describing manifest for runtime discovery.

## Error handling strategy

A single consistent contract across all tools (enforced by the
`mcp-tool-conventions` steering doc):

- Tools return `dict` or `list[dict]`; failures carry an `error` key.
- Network calls catch `requests.RequestException`; parsing catches
  `ValueError`/`json.JSONDecodeError`/`yaml.YAMLError`; a top-level
  `except Exception` guarantees nothing escapes.
- Input is validated early (e.g. `_parse_repo_url` raises `ValueError`, caught
  and returned as an `error`).
- Best-effort sub-steps (issue comments, raw-content previews) swallow their own
  errors and continue.

## Cross-cutting rules

- Secrets (`github_token`, `auth_token`) are optional parameters, never
  hardcoded or logged.
- Expensive work is capped (`urls[:5]`, `max_files`, `max_pages`,
  `per_page=min(n, 100)`).
- Output is Markdown or structured dicts — never raw HTML.

## Deployment

- **Dockerfile**: 3-stage multistage build.
  1. `deps` — `pip install` into `/install/pkgs` (isolates build toolchain).
  2. `browsers` — `scrapling install` downloads browser binaries to
     `/ms-playwright`.
  3. `runtime` — lean final image: runtime libs + packages + browsers + `app/`,
     running as non-root `appuser`, `CMD python -m app.server`.
- **Health**: load balancer / Lightsail probes `GET /healthz`.
- **CI**: `.github/workflows/` builds and publishes the image.

## Testing strategy

- `tests/test_<module>.py` mirrors each tool module; fixtures in `conftest.py`.
- All network I/O is mocked — no live calls in tests.
- Both success and `error` shapes are covered. Coverage gate: 80%
  (`pyproject.toml`).

## Non-goals

- No vector embedding/storage (client's responsibility).
- No auth layer inside the server (handled at network/deployment level).
- No browser automation beyond Scrapling's `StealthyFetcher`.
