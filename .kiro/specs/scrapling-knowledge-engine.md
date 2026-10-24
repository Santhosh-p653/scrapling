# Spec: Scrapling Knowledge Engine — MCP Server

## Overview

A FastMCP server that provides agents and IDEs with a unified toolkit for knowledge base ingestion, web scraping, browser automation, API introspection, and GitHub/repo ingestion. Runs over `streamable-http` on port `8080` and is registered as a user-level MCP server in Kiro IDE.

---

## Goals

- Give AI agents a single MCP endpoint to ingest knowledge from any source: web pages, docs sites, GitHub repos, OpenAPI/GraphQL specs, PDFs
- Support both fast HTTP scraping and stealth browser-based extraction for bot-protected sites
- Provide context compression and bundling so agents can inject knowledge within token budgets
- Enable dynamic tool selection by exposing a self-describing tool manifest

---

## Current Features (Implemented)

### Phase 0 — Core Scraping

| Tool | Description |
|---|---|
| `search_web` | Anonymous DuckDuckGo search, returns title + URL + snippet |
| `fetch_page_knowledge` | Fast HTTP page fetch → clean LLM markdown |
| `fetch_stealth_knowledge` | Headless browser fetch bypassing Cloudflare/Akamai |
| `batch_knowledge_extract` | Batch fetch up to 5 URLs in one call |
| `GET /healthz` | Health check endpoint for Lightsail / load balancers |

### Phase 1 — Repo & API Ingestion ✅

| Tool | Description |
|---|---|
| `ingest_github_repo` | Fetches full file tree + raw content for matched extensions |
| `fetch_github_file` | Fetches a single raw file from any GitHub repo |
| `fetch_github_issues` | Pulls issues with title, body, labels, and comments |
| `search_github_code` | GitHub code search with repo/language filters + content preview |
| `fetch_openapi_spec` | Parses OpenAPI 3.x / Swagger 2.x JSON or YAML → summarised endpoint map |
| `fetch_graphql_schema` | Runs introspection query → structured types, queries, mutations |

---

## Planned Features

### Phase 2 — Docs & Site Crawling (Priority: High)

#### `ingest_github_repo`
- Input: `repo_url: str`, `branch: str = "main"`, `file_extensions: list[str] = [".py", ".md", ".ts", ".js"]`, `max_files: int = 50`
- Uses GitHub REST API (`/repos/{owner}/{repo}/git/trees/{branch}?recursive=1`) to list all files
- Fetches raw content for each matched file
- Returns list of `{ path, language, content, char_count }`
- Supports public repos; private repos via optional `github_token` param
- Auto-fallbacks from `main` → `master` on 404

#### `fetch_github_file`
- Input: `repo_url: str`, `file_path: str`, `branch: str = "main"`, `github_token: str = None`
- Fetches a single raw file from any GitHub repo
- Returns `{ path, content, language }`
- Auto-fallbacks from `main` → `master` on 404

#### `fetch_github_issues`
- Input: `repo_url: str`, `state: str = "open"`, `max_issues: int = 20`, `github_token: str = None`
- Pulls issues with title, body, labels, comments (skips PRs automatically)
- Returns structured list for agent context

#### `fetch_openapi_spec`
- Input: `url: str`
- Fetches and parses OpenAPI 3.x / Swagger 2.x JSON or YAML
- Returns summarized tool-map: `{ title, version, base_url, endpoint_count, endpoints: [{ path, method, summary, parameters, request_body, responses }] }`
- Agents use this to understand an API before calling it

#### `fetch_graphql_schema`
- Input: `url: str`, `headers: dict = {}`
- Sends a full introspection query to a GraphQL endpoint
- Returns `{ query_type, mutation_type, queries, mutations, subscriptions, types }`
- Each field includes name, type signature, args, description, and deprecation status

#### `search_github_code`
- Input: `query: str`, `repo: str = None`, `language: str = None`, `max_results: int = 10`, `github_token: str = None`
- GitHub code search API wrapper (authentication recommended for reliable results)
- Returns matching file snippets with repo, path, language, and 2000-char content preview

#### `scrape_docs_site`
- Input: `start_url: str`, `max_pages: int = 20`, `same_domain_only: bool = True`
- Crawls a documentation site following internal links up to `max_pages`
- Returns list of `{ url, title, content_markdown }`
- Skips nav/footer/sidebar noise

#### `scrape_sitemap`
- Input: `sitemap_url: str`, `max_urls: int = 50`
- Parses `sitemap.xml` (including sitemap index files)
- Batch-fetches all URLs and returns structured markdown per page
- Good for ingesting entire docs sites in one call

#### `fetch_pdf_content`
- Input: `url: str`, `max_length: int = 10000`
- Downloads PDF and extracts text using `pypdf` or `pdfminer`
- Returns clean text ready for chunking/ingestion

---

### Phase 3 — Context Management (Priority: Medium)

#### `build_context_bundle`
- Input: `sources: list[str]` (URLs, repo URLs, or search queries), `topic: str`, `max_tokens: int = 4000`
- Orchestrates fetching across multiple sources using the right tool per source type
- Chunks, ranks by relevance to `topic`, and returns a single ready-to-inject context block

#### `summarize_for_context`
- Input: `content: str`, `target_length: int = 2000`
- Compresses raw extracted content to a target char budget
- Preserves headings, code blocks, and key paragraphs
- Strips boilerplate, repetition, and nav noise

#### `detect_content_type`
- Input: `url: str`
- Identifies what kind of content a URL contains: `docs_site`, `github_repo`, `openapi_spec`, `graphql_endpoint`, `pdf`, `blog_post`, `generic_page`
- Returns `{ type, confidence, suggested_tool }`
- Enables agents to auto-route URLs to the correct ingestion tool

---

### Phase 4 — Live API & Tool Calling (Priority: Medium)

#### `call_rest_api`
- Input: `url: str`, `method: str = "GET"`, `headers: dict = {}`, `body: dict = {}`, `auth_token: str = None`
- Generic authenticated REST caller
- Returns `{ status_code, response_json_or_text }`

#### `list_available_tools`
- No input required
- Returns a structured manifest of all tools in this MCP server
- Includes name, description, input schema, and example usage
- Lets agents dynamically discover what's available without out-of-band docs

#### `search_github_code`
- Input: `query: str`, `repo: str = None`, `language: str = None`, `max_results: int = 10`, `github_token: str = None`
- GitHub code search API wrapper
- Returns matching file snippets with repo, path, and line context

---

## Technical Architecture

```
app/
  server.py          # Main FastMCP server — registers all tools
  __init__.py
  tools/
    __init__.py
    search.py        # search_web
    scrape.py        # fetch_page_knowledge, fetch_stealth_knowledge, batch_knowledge_extract
    github.py        # ingest_github_repo, fetch_github_file, fetch_github_issues, search_github_code  ✅ Phase 1
    api.py           # fetch_openapi_spec, fetch_graphql_schema                                         ✅ Phase 1
    crawl.py         # scrape_docs_site, scrape_sitemap                                                 Phase 2
    documents.py     # fetch_pdf_content                                                                Phase 2
    context.py       # build_context_bundle, summarize_for_context, detect_content_type                 Phase 3
    manifest.py      # list_available_tools                                                              Phase 4
```

---

## Dependencies

```
# Phase 0 (core)
fastmcp>=3.4.0
scrapling>=0.3.0
duckduckgo_search>=7.0.0
markdownify>=0.13.0
uvicorn>=0.30.0

# Phase 1 ✅
PyYAML>=6.0          # OpenAPI YAML parsing
requests>=2.31.0     # GitHub API calls (sync, lightweight)

# Phase 2
pypdf>=4.0.0         # PDF text extraction
beautifulsoup4>=4.12 # Sitemap XML parsing

# Phase 3 & 4
# No new deps — uses existing scrapling + markdownify
```

---

## Non-Goals

- No vector embedding or storage (this server provides raw/cleaned content; embedding is the agent's job)
- No authentication layer on the MCP server itself (handled at the deployment/network level)
- No browser automation beyond what Scrapling's StealthyFetcher provides (no Playwright/Selenium)

---

## Success Criteria

- All tools return consistent `dict` or `list[dict]` shapes with an `error` key on failure
- Every tool handles exceptions gracefully — never crashes the server
- `ingest_github_repo` can pull a 50-file repo in under 10 seconds on average
- `build_context_bundle` produces output that fits within a 4k token window by default
- Server registered and accessible in Kiro IDE as `scrapling-mcp`
