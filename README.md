# Scrapling Knowledge Engine — MCP Server

> A FastMCP server that gives AI agents and IDEs a single endpoint for knowledge ingestion: web scraping, docs-site crawling, GitHub/repo ingestion, API introspection, PDF extraction, and context bundling — all returned as clean, LLM-ready data.

[![AWS](https://img.shields.io/badge/AWS-Lightsail-orange?logo=amazon-aws)](https://aws.amazon.com/lightsail/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker)](https://www.docker.com/)
[![Scrapling](https://img.shields.io/badge/Scrapling-Web%20Extraction-green)](https://scrapling.readthedocs.io/)

## Overview

Modern AI applications constantly need fresh, structured, external knowledge. Rather than reimplementing scraping, repo ingestion, and API discovery inside every RAG system or agent, this project exposes those capabilities through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

The server started as a [Scrapling](https://scrapling.readthedocs.io/)-powered web extractor and has grown into a full **knowledge engine**: 18 tools spanning search, scraping, crawling, GitHub, API introspection, document extraction, and context assembly. It runs over `streamable-http` on port `8080` and plugs into any MCP-compatible client.

```
┌──────────────────────┐
│   AI IDE / AI Agent   │
│  Kiro / MCP Client    │
└──────────┬────────────┘
           │ MCP (streamable-http :8080)
           ▼
┌──────────────────────────────────────┐
│       Scrapling Knowledge Engine       │
│  search · scrape · crawl · github ·    │
│  api · pdf · context · manifest        │
└──────────┬────────────────────────────┘
           ▼
   Web · Docs · GitHub · REST/GraphQL · PDFs
           ▼
     Clean Markdown / Structured JSON
           ▼
   RAG · Embeddings · Vector DB · Agent Memory
```

## Tool Catalog (18 tools)

The server is organized into five phases. Every tool returns a consistent `dict` or `list[dict]` shape with an `error` key on failure, and never crashes the server.

### Phase 0 — Core Scraping

| Tool | Description |
|---|---|
| `search_web` | Anonymous DuckDuckGo search → title + URL + snippet |
| `fetch_page_knowledge` | Fast HTTP page fetch → clean LLM markdown |
| `fetch_stealth_knowledge` | Headless browser fetch bypassing Cloudflare/Akamai |
| `batch_knowledge_extract` | Batch fetch up to 5 URLs in one call |

### Phase 1 — Repo & API Ingestion

| Tool | Description |
|---|---|
| `ingest_github_repo` | Full file tree + raw content for matched extensions (public & private via token) |
| `fetch_github_file` | Fetch a single raw file from any repo (auto `main`→`master` fallback) |
| `fetch_github_issues` | Issues with title, body, labels, comments (PRs skipped) |
| `search_github_code` | GitHub code search with repo/language filters + content preview |
| `fetch_openapi_spec` | Parse OpenAPI 3.x / Swagger 2.x (JSON or YAML) → summarised endpoint map |
| `fetch_graphql_schema` | Introspection query → structured types, queries, mutations |

### Phase 2 — Docs & Site Crawling

| Tool | Description |
|---|---|
| `scrape_docs_site` | BFS crawl following internal links → clean markdown per page |
| `scrape_sitemap` | Parse `sitemap.xml` (incl. index files) → batch-fetch pages as markdown |
| `fetch_pdf_content` | Download a PDF → extract clean text via `pypdf` (handles encryption) |

### Phase 3 — Context Management

| Tool | Description |
|---|---|
| `detect_content_type` | Classify a URL (docs/repo/openapi/graphql/pdf/blog/generic) → suggested tool |
| `summarize_for_context` | Compress content to a char budget, preserving headings + code blocks |
| `build_context_bundle` | Multi-source ingest → chunk → rank by topic → single budgeted context block |

### Phase 4 — Live API & Tool Calling

| Tool | Description |
|---|---|
| `call_rest_api` | Generic authenticated REST caller (any verb, bearer auth, JSON/text decode) |
| `list_available_tools` | Self-describing manifest of all tools (name, schema, example) via introspection |

### Health Check

| Endpoint | Description |
|---|---|
| `GET /healthz` | Health check for Lightsail / load balancers |

## Project Structure

```
.
├── app/
│   ├── server.py              # FastMCP server — registers all 18 tools
│   ├── __init__.py
│   └── tools/
│       ├── __init__.py
│       ├── search.py          # search_web
│       ├── scrape.py          # fetch_page_knowledge, fetch_stealth_knowledge, batch_knowledge_extract
│       ├── github.py          # ingest_github_repo, fetch_github_file, fetch_github_issues, search_github_code
│       ├── api.py             # fetch_openapi_spec, fetch_graphql_schema, call_rest_api
│       ├── crawl.py           # scrape_docs_site, scrape_sitemap
│       ├── documents.py       # fetch_pdf_content
│       ├── context.py         # build_context_bundle, summarize_for_context, detect_content_type
│       └── manifest.py        # list_available_tools
├── tests/                     # pytest suite (mocked, offline)
├── .github/workflows/         # CI: test + build/push to GHCR
├── Dockerfile
├── requirements.txt
├── pyproject.toml             # pytest + coverage config
└── README.md
```

## Technology Stack

| Component | Technology |
|---|---|
| Protocol | Model Context Protocol (MCP) via FastMCP |
| Web Extraction | Scrapling (HTTP + stealth browser) |
| HTML → Markdown | markdownify |
| Search | duckduckgo_search |
| API parsing | PyYAML (OpenAPI), requests (REST/GraphQL) |
| Crawling | BeautifulSoup + lxml (sitemap parsing) |
| Documents | pypdf |
| Language | Python 3.11+ |
| Containerization | Docker |
| Cloud | AWS Lightsail |
| CI/CD | GitHub Actions → GHCR |

## Running Locally

**1. Clone the repository**

```bash
git clone https://github.com/Santhosh-p653/scrapling.git
cd scrapling
```

**2. Create a virtual environment and install dependencies**

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt

# Download browser binaries for Scrapling stealth mode
scrapling install
```

**3. Run the server**

```bash
python -m app.server
```

The server starts on `http://0.0.0.0:8080` with the MCP endpoint at `/mcp` and a health check at `/healthz`.

## Run with Docker

Build the image:

```bash
docker build -t scrapling-mcp .
```

Run the container:

```bash
docker run -d \
  --name scrapling-mcp \
  -p 8080:8080 \
  scrapling-mcp
```

Check health:

```bash
curl http://localhost:8080/healthz
```

## Connecting to Kiro (or any MCP client)

Add the server to your MCP config (`~/.kiro/settings/mcp.json` for user-level, or `.kiro/settings/mcp.json` for workspace-level):

```json
{
  "mcpServers": {
    "scrapling-mcp": {
      "url": "http://localhost:8080/mcp",
      "disabled": false
    }
  }
}
```

Then start the server (`python -m app.server`) and the client will discover all 18 tools. Call `list_available_tools` from the client to get the full self-describing manifest.

## Testing

Tests are fully mocked and run offline (no live network needed).

```bash
pip install pytest pytest-cov pytest-mock
pytest tests/ --cov=app --cov-report=term-missing
```

Coverage config and an 80% gate live in `pyproject.toml`.

## CI/CD — GitHub Actions → GHCR

`.github/workflows/docker-publish.yml` runs two jobs:

1. **test** — installs deps, runs pytest with coverage (80% gate).
2. **build-and-push** — on push to `main` or a `v*.*.*` tag, builds the image and pushes to GitHub Container Registry (`ghcr.io/<owner>/<repo>`) with `latest`, `sha-<short>`, and semver tags.

Pull requests run tests only; images are published on merges and tags.

## Deploy to AWS Lightsail

```
GitHub → push → GitHub Actions → test → build → GHCR → Lightsail container service
                                                              ▼
                                                 Scrapling Knowledge Engine
                                                              ▼
                                                   MCP-compatible AI clients
```

1. Create an AWS Lightsail container service.
2. Point it at the image published to GHCR by CI (or build and push manually).
3. Expose port `8080` and set the health check path to `/healthz`.
4. Keep any secrets (e.g. `GITHUB_TOKEN` for private repo ingestion) in environment variables, never in the repo.

## Example Agent Workflows

**Research a topic across many sources in one call:**

```python
build_context_bundle(
    sources=[
        "https://github.com/pallets/flask",      # repo → ingest_github_repo
        "https://flask.palletsprojects.com/",     # docs → scrape_docs_site
        "flask blueprints best practices",        # bare string → search_web
    ],
    topic="flask blueprints and app factories",
    max_tokens=4000,
)
```

**Discover and call an API:**

```python
spec = fetch_openapi_spec("https://api.example.com/openapi.json")
# agent reads the endpoint map, then:
call_rest_api(
    url="https://api.example.com/v1/users",
    method="POST",
    body={"name": "Ada"},
    auth_token="...",
)
```

**Let the agent auto-route an unknown URL:**

```python
route = detect_content_type("https://example.com/paper.pdf")
# → { "type": "pdf", "suggested_tool": "fetch_pdf_content", ... }
```

## Design Principles

- **Consistent shapes** — every tool returns `dict`/`list[dict]` with an `error` key on failure.
- **Never crashes** — all tools handle exceptions gracefully.
- **No storage layer** — the server returns raw/cleaned content; embedding and indexing are the agent's job.
- **No auth on the server itself** — handle authentication at the deployment/network level.
- **Modular** — each tool category lives in its own module under `app/tools/`.

## Security Considerations

- Use HTTPS in production and restrict network access.
- Validate/allowlist requested URLs where appropriate.
- Keep tokens and secrets in environment variables or a secrets manager.
- Apply rate limits and monitor resource consumption.
- Respect target sites' terms of service and applicable laws.

## Future Improvements

- [ ] Authentication / access control for MCP clients
- [ ] URL/domain allowlisting
- [ ] Content caching
- [ ] Vector DB integration for persistent knowledge
- [ ] Crawl scheduling and queue-based ingestion
- [ ] Observability dashboard

## Author

**Santhosh P** — building around AI Agents, RAG, MCP, cloud infrastructure, and web data pipelines.

GitHub: [@Santhosh-p653](https://github.com/Santhosh-p653)

---

> **Key Idea:** Deploy the knowledge engine once. Plug it into any AI workflow that needs fresh, structured external knowledge — web, docs, repos, APIs, or PDFs — all through one MCP endpoint.
