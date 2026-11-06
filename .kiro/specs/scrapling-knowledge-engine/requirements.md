# Requirements — Scrapling Knowledge Engine

## Introduction

The Scrapling Knowledge Engine is a FastMCP server that gives AI agents and IDEs
a single endpoint for ingesting external knowledge: web pages, docs sites,
GitHub repositories, OpenAPI/GraphQL specs, PDFs, and live REST APIs. It
normalizes everything into LLM-ready Markdown or structured dicts so clients can
chunk, embed, and retrieve without reimplementing scraping.

The server runs over `streamable-http` on port `8080`, is containerized with
Docker, and targets AWS Lightsail.

## Requirements

### Requirement 1 — Web content extraction

**User story:** As an AI agent, I want to extract clean content from any web
page, so that I can feed structured knowledge into my reasoning without parsing
raw HTML.

#### Acceptance criteria

1. WHEN a tool is given a URL THEN the system SHALL return a title, the source
   URL, a character count, and Markdown content.
2. WHEN a page exceeds the caller's `max_length` budget THEN the system SHALL
   truncate the output and append a clear truncation marker.
3. WHEN HTML is converted THEN the system SHALL strip `script`, `style`, `nav`,
   `footer`, and `aside` noise.
4. WHEN a site uses aggressive bot protection THEN the system SHALL offer a
   stealth browser-based extraction path.
5. WHEN a caller supplies up to 5 URLs THEN the system SHALL support extracting
   them in a single batch call.

### Requirement 2 — Web search

**User story:** As an AI agent, I want to search the live web, so that I can
discover current sources before extracting them.

#### Acceptance criteria

1. WHEN given a query THEN the system SHALL return a list of results with title,
   URL, and snippet.
2. WHEN a result count is requested THEN the system SHALL respect the
   `max_results` limit.
3. WHEN search fails THEN the system SHALL return a list containing an error
   entry rather than raising.

### Requirement 3 — GitHub & repository ingestion

**User story:** As an AI agent, I want to pull source, files, and issues from a
GitHub repo, so that I can reason about a codebase.

#### Acceptance criteria

1. WHEN given a repo URL or `owner/repo` shorthand THEN the system SHALL parse
   the owner and repo name, returning an error on malformed input.
2. WHEN a repo is ingested THEN the system SHALL return matched files with path,
   detected language, content, and char count, bounded by `max_files`.
3. WHEN the `main` branch returns 404 THEN the system SHALL fall back to
   `master`.
4. WHEN issues are fetched THEN the system SHALL exclude pull requests and
   include labels and comments on a best-effort basis.
5. WHEN a private resource is accessed THEN the system SHALL accept an optional
   `github_token` and never hardcode or echo it.

### Requirement 4 — API introspection & calling

**User story:** As an AI agent, I want to understand and call external APIs, so
that I can use them as tools after discovering their shape.

#### Acceptance criteria

1. WHEN given an OpenAPI 3.x or Swagger 2.x URL (JSON or YAML) THEN the system
   SHALL return a summarized endpoint map (path, method, summary, parameters,
   request body, responses).
2. WHEN given a GraphQL endpoint THEN the system SHALL run introspection and
   return query/mutation/subscription types with field signatures.
3. WHEN asked to call a REST endpoint THEN the system SHALL support GET, POST,
   PUT, PATCH, DELETE, HEAD, OPTIONS and return status, ok flag, headers, and
   decoded body.
4. WHEN an unsupported HTTP method is requested THEN the system SHALL return an
   error without making a request.

### Requirement 5 — Docs crawling & documents

**User story:** As an AI agent, I want to ingest whole docs sites and PDFs, so
that I can build a knowledge base from long-form sources.

#### Acceptance criteria

1. WHEN given a start URL THEN the system SHALL crawl internal links up to a
   `max_pages` bound and return per-page Markdown.
2. WHEN given a sitemap URL THEN the system SHALL parse it (including index
   files) and batch-fetch pages up to a limit.
3. WHEN given a PDF URL THEN the system SHALL extract clean text within a length
   budget, handling encrypted PDFs gracefully.

### Requirement 6 — Context management

**User story:** As an AI agent, I want content routed, compressed, and bundled,
so that it fits my token budget.

#### Acceptance criteria

1. WHEN given a URL THEN the system SHALL classify its content type and suggest
   the appropriate ingestion tool with a confidence signal.
2. WHEN given content and a target length THEN the system SHALL compress it while
   preserving headings and code blocks.
3. WHEN given multiple sources and a topic THEN the system SHALL ingest, chunk,
   rank by relevance, and return a single budgeted context block.

### Requirement 7 — Tool discovery

**User story:** As an AI agent, I want to discover available tools at runtime,
so that I can plan without out-of-band documentation.

#### Acceptance criteria

1. WHEN requested THEN the system SHALL return a manifest of all tools with name,
   description, input schema, and example usage.

### Requirement 8 — Reliability & operability

**User story:** As an operator, I want the server to stay up and be observable,
so that it runs reliably behind a load balancer.

#### Acceptance criteria

1. WHEN any tool encounters an error THEN the system SHALL return a structured
   error value and SHALL NOT crash the server.
2. WHEN every tool runs THEN it SHALL return a `dict` or `list[dict]` with an
   `error` key on failure.
3. WHEN `GET /healthz` is called THEN the system SHALL return a healthy status
   payload with a UTC timestamp.
4. WHEN the server starts THEN it SHALL listen on `streamable-http` at
   `0.0.0.0:8080`.
