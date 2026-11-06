# Project Structure

## Layout

```
.
├── app/
│   ├── __init__.py
│   ├── server.py              # FastMCP server — registers every tool, defines /healthz
│   └── tools/
│       ├── __init__.py
│       ├── search.py          # search_web
│       ├── scrape.py          # fetch_page_knowledge, fetch_stealth_knowledge, batch_knowledge_extract
│       ├── github.py          # ingest_github_repo, fetch_github_file, fetch_github_issues, search_github_code
│       ├── api.py             # fetch_openapi_spec, fetch_graphql_schema, call_rest_api
│       ├── crawl.py           # scrape_docs_site, scrape_sitemap
│       ├── documents.py       # fetch_pdf_content
│       ├── context.py         # detect_content_type, summarize_for_context, build_context_bundle
│       └── manifest.py        # list_available_tools
├── tests/                     # pytest suite, one test module per tool module
├── Dockerfile                 # 3-stage multistage build
├── requirements.txt           # pinned runtime deps
├── pyproject.toml             # package metadata, pytest + coverage config
└── .github/workflows/         # CI / Docker publish
```

## Where things go

- **New tool** → add the function to the matching module in `app/tools/`. Group by
  concern (scraping, github, api, crawl, documents, context). If it's a new
  concern, create a new module.
- **Registering a tool** → import it in `app/server.py` and register with
  `mcp.tool()(your_function)` under the correct phase comment block.
- **Tests** → mirror the module name: `app/tools/api.py` → `tests/test_api.py`.
  Shared fixtures live in `tests/conftest.py`.

## Server organization

`server.py` groups tool registration into phase blocks:

- Phase 0 — Core Scraping (search + page/stealth/batch extraction)
- Phase 1 — Repo & API Ingestion (GitHub + OpenAPI/GraphQL)
- Phase 2 — Docs & Site Crawling (docs crawl, sitemap, PDF)
- Phase 3 — Context Management (detect, summarize, bundle)
- Phase 4 — Live API & Tool Calling (REST caller, tool manifest)

Keep new registrations inside the relevant block so the server stays readable.

## Naming conventions

- Tool functions use `snake_case` verbs describing the action
  (`fetch_*`, `search_*`, `ingest_*`, `scrape_*`, `build_*`, `detect_*`).
- Private helpers in a tool module are prefixed with `_` (e.g. `_parse_repo_url`,
  `_detect_language`, `_unwrap_type`).
- Every public tool has a docstring — it becomes the MCP tool description the
  agent sees, so write it for an agent audience.
