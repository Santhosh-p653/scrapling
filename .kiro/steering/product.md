# Product

## What this is

The **Scrapling Knowledge Engine** is a FastMCP server that gives AI agents and
IDEs a single endpoint for ingesting external knowledge. Instead of every RAG
pipeline or agent re-implementing scraping, this server exposes web extraction,
GitHub/repo ingestion, API introspection, document parsing, and context
management as reusable MCP tools.

The core idea: acquire external knowledge in a form (clean Markdown / structured
dicts) that can flow directly into an LLM pipeline — chunk, embed, index,
retrieve.

## Who uses it

- **AI IDEs** (e.g. MCP-compatible coding assistants) that need live web/doc lookup
- **RAG systems** that need a fresh ingestion layer
- **AI agents** that discover and call tools dynamically
- **Research / automation workflows**

## What it deliberately does NOT do

- No vector embedding or storage — it returns raw/cleaned content; embedding is
  the client's job
- No auth layer inside the MCP server — handled at the deployment/network level
- No browser automation beyond Scrapling's `StealthyFetcher` (no raw
  Playwright/Selenium orchestration)

## Deployment shape

Runs over `streamable-http` on port `8080`, containerized with Docker, and
deployed on AWS Lightsail. A `GET /healthz` route backs load-balancer health
checks.

## Design values

- Every tool returns a predictable shape and never crashes the server
- Output is LLM-ready Markdown or structured dicts, not raw HTML
- The server is a shared capability: deploy once, reuse across many clients
