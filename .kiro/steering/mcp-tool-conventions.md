---
inclusion: fileMatch
fileMatchPattern: 'app/**/*.py'
---

# MCP Tool Conventions

Rules for writing and registering tools in this FastMCP server. Follow these so
every tool behaves predictably for the agents that call it.

## Return shape

- A tool returns either a `dict` or a `list[dict]`. Never return bare strings,
  `None`, or raise out of the tool body.
- On failure, return an error sentinel instead of raising:
  - single-result tools → `{"error": "<message>"}`
  - list-result tools → `[{"error": "<message>"}]`
- Keep keys stable and descriptive. Successful results use domain keys
  (`title`, `url`, `content`, `endpoints`, ...); failures carry `error` (plus an
  optional `detail`).

## Error handling

- Wrap the whole tool body so no exception escapes. Catch the narrowest useful
  exception type:
  - network calls → `except requests.RequestException`
  - JSON/YAML parsing → `except (ValueError, json.JSONDecodeError)` / `yaml.YAMLError`
  - everything else at the top level → `except Exception as e` returning
    `{"error": f"...: {str(e)}"}`
- Validate and parse inputs early (see `_parse_repo_url`) and return a clean
  `error` dict on bad input rather than letting it fail deep in the call.
- Best-effort sub-steps (e.g. fetching issue comments) should swallow their own
  errors and continue, not fail the whole tool.

## Signatures & types

- Use explicit type hints on every parameter and the return value.
- Give sane defaults so agents can call with minimal args
  (`max_results: int = 5`, `branch: str = "main"`, `max_length: int = 6000`).
- Optional secrets (e.g. `github_token: str | None = None`) are parameters, never
  hardcoded. Never log or echo token values.
- Cap expensive work with explicit limits (`urls[:5]`, `max_files`,
  `max_pages`, `per_page=min(n, 100)`).

## Output content rules

- Convert HTML to Markdown with `markdownify`, stripping `script`, `style`,
  `nav`, `footer`, `aside`.
- Respect a `max_length` budget and append a clear truncation marker when cut.
- Prefer `article` → `main` → `#content` → `body` selector fallback for main
  content extraction.

## Docstrings are the agent-facing contract

- Every registered tool needs a docstring: one line on what it does, then the
  args and the return shape. FastMCP surfaces this to the model, so write it for
  an agent deciding whether to call the tool.

## Registration

- Register in `app/server.py` with `mcp.tool()(function_name)` under the correct
  phase comment block.
- Keep imports grouped by tool module at the top of `server.py`.

## Testing

- Add a test in `tests/test_<module>.py` mirroring the module name.
- Mock all network I/O (`requests`, fetchers) — tests must not hit the network.
- Cover both the success shape and the `error` shape. Coverage gate is 80%.
