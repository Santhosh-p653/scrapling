# Implementation Plan — Scrapling Knowledge Engine

All core phases are implemented. Checked items reflect shipped functionality;
unchecked items are hardening/backlog work from the README's "Future
Improvements".

## Phase 0 — Core scraping

- [x] 1. Scaffold FastMCP server with `/healthz` and `streamable-http` on :8080
  - _Requirements: 8.3, 8.4_
- [x] 2. Implement `search_web` (DuckDuckGo)
  - _Requirements: 2.1, 2.2, 2.3_
- [x] 3. Implement `fetch_page_knowledge` (fast HTTP → Markdown)
  - _Requirements: 1.1, 1.2, 1.3_
- [x] 4. Implement `fetch_stealth_knowledge` (StealthyFetcher)
  - _Requirements: 1.4_
- [x] 5. Implement `batch_knowledge_extract` (≤5 URLs)
  - _Requirements: 1.5_

## Phase 1 — Repo & API ingestion

- [x] 6. Implement GitHub helpers (`_parse_repo_url`, `_gh_headers`, `_detect_language`)
  - _Requirements: 3.1_
- [x] 7. Implement `ingest_github_repo` with `main→master` fallback
  - _Requirements: 3.2, 3.3, 3.5_
- [x] 8. Implement `fetch_github_file` and `fetch_github_issues` (skip PRs, comments best-effort)
  - _Requirements: 3.3, 3.4, 3.5_
- [x] 9. Implement `search_github_code`
  - _Requirements: 3.5_
- [x] 10. Implement `fetch_openapi_spec` (JSON/YAML, OpenAPI 3.x + Swagger 2.x)
  - _Requirements: 4.1_
- [x] 11. Implement `fetch_graphql_schema` with `_unwrap_type`
  - _Requirements: 4.2_

## Phase 2 — Docs & site crawling

- [x] 12. Implement `scrape_docs_site` (BFS, same-domain, max_pages)
  - _Requirements: 5.1_
- [x] 13. Implement `scrape_sitemap` (incl. index files)
  - _Requirements: 5.2_
- [x] 14. Implement `fetch_pdf_content` (pypdf, encryption-safe)
  - _Requirements: 5.3_

## Phase 3 — Context management

- [x] 15. Implement `detect_content_type`
  - _Requirements: 6.1_
- [x] 16. Implement `summarize_for_context`
  - _Requirements: 6.2_
- [x] 17. Implement `build_context_bundle`
  - _Requirements: 6.3_

## Phase 4 — Live API & tool calling

- [x] 18. Implement `call_rest_api` (method allowlist, JSON/text decode)
  - _Requirements: 4.3, 4.4_
- [x] 19. Implement `list_available_tools` manifest
  - _Requirements: 7.1_

## Cross-cutting

- [x] 20. Enforce consistent `dict`/`list[dict]` + `error` contract across all tools
  - _Requirements: 8.1, 8.2_
- [x] 21. Multistage Dockerfile (deps / browsers / runtime, non-root)
  - _Requirements: 8.4_
- [x] 22. Pytest suite mirroring tool modules, network mocked, 80% coverage gate
  - _Requirements: 8.1, 8.2_

## Backlog — hardening (not yet implemented)

- [ ] 23. Add MCP client authentication
  - _Requirements: 8 (operability)_
- [ ] 24. Add URL/domain allowlisting and request validation
  - _Requirements: 8.1_
- [ ] 25. Add content caching to cut repeat fetches
- [ ] 26. Add rate limiting and request logging/observability
- [ ] 27. Add retry policies for flaky upstreams
