# Tech Stack & Commands

## Language & runtime

- **Python 3.11+** (required; see `pyproject.toml` `requires-python`)
- Package metadata in `pyproject.toml`; pinned runtime deps in `requirements.txt`

## Core libraries

| Concern | Library |
|---|---|
| MCP server framework | `fastmcp>=3.4.0` |
| Web extraction (fast HTTP) | `scrapling>=0.3.0` (`Fetcher`) |
| Web extraction (stealth browser) | `scrapling` (`StealthyFetcher`) + `patchright`, `browserforge` |
| HTML → Markdown | `markdownify>=0.13.0` |
| Anonymous web search | `duckduckgo_search>=7.0.0` |
| HTTP client (GitHub / REST / specs) | `requests`, `curl_cffi` |
| OpenAPI YAML parsing | `PyYAML>=6.0` |
| PDF text extraction | `pypdf>=4.0.0` |
| Sitemap / XML parsing | `beautifulsoup4>=4.12`, `lxml>=5.0.0` |
| ASGI server | `uvicorn>=0.30.0` |

## Transport

The server runs over `streamable-http` on `0.0.0.0:8080`. Entry point is
`app/server.py` (`mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)`).

## Commands

Always target Windows PowerShell syntax (use `;` not `&&` to chain).

### Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
scrapling install    # downloads browser binaries for StealthyFetcher
```

### Run locally

```powershell
python -m app.server
```

### Tests

Test deps are an optional extra; install with `pip install -e ".[test]"`.

```powershell
pytest                       # run full suite (config in pyproject.toml)
pytest tests/test_api.py     # run one module
pytest --cov                 # with coverage (fail_under = 80)
```

Use `--run`-style single execution, never watch mode, in automation.

### Docker

```powershell
docker build -t scrapling-mcp .
docker run -d --name scrapling-mcp -p 8080:8080 scrapling-mcp
```

The Dockerfile is a 3-stage multistage build: `deps` (pip install into a
prefix), `browsers` (`scrapling install`), and `runtime` (lean final image,
non-root `appuser`).

## Conventions

- Prefer stdlib + the libraries above; do not introduce a new HTTP client or
  parser when `requests` / `beautifulsoup4` already cover the need.
- Pin or constrain new dependencies in both `requirements.txt` and
  `pyproject.toml`.
- Coverage gate is 80% (`[tool.coverage.report] fail_under = 80`).
