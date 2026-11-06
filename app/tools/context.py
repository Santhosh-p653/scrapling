import re
from urllib.parse import urlparse

from app.tools.search import search_web
from app.tools.scrape import fetch_page_knowledge
from app.tools.crawl import scrape_docs_site
from app.tools.documents import fetch_pdf_content
from app.tools.github import ingest_github_repo, _parse_repo_url
from app.tools.api import fetch_openapi_spec, fetch_graphql_schema


# ---------------------------------------------------------------------------
# Tool: detect_content_type
# ---------------------------------------------------------------------------

# Hints used to classify a URL into a routing category
_DOCS_HINTS = ("/docs", "/documentation", "readthedocs", "docusaurus", "/guide", "/reference", "/api-docs")
_BLOG_HINTS = ("/blog", "/post", "/article", "medium.com", "dev.to", "substack", "hashnode")
_GRAPHQL_HINTS = ("/graphql", "/gql")
_OPENAPI_HINTS = ("openapi", "swagger", "/v2/api-docs", "/v3/api-docs")


def detect_content_type(url: str) -> dict:
    """
    Classifies what kind of content a URL points to so agents can auto-route
    it to the correct ingestion tool.

    Returns:
      { type, confidence, suggested_tool }
    where type is one of:
      docs_site | github_repo | openapi_spec | graphql_endpoint | pdf | blog_post | generic_page
    """
    if not url or not isinstance(url, str):
        return {"type": "generic_page", "confidence": 0.0, "suggested_tool": "fetch_page_knowledge"}

    lowered = url.lower()
    parsed = urlparse(lowered)
    netloc = parsed.netloc
    path = parsed.path

    # PDF — strongest signal is a file extension
    if lowered.endswith(".pdf"):
        return {"type": "pdf", "confidence": 0.98, "suggested_tool": "fetch_pdf_content"}

    # GitHub repo
    if "github.com" in netloc:
        # Distinguish a repo root from a blob/issues/etc. — still route to repo ingest
        try:
            _parse_repo_url(url)
            return {"type": "github_repo", "confidence": 0.95, "suggested_tool": "ingest_github_repo"}
        except ValueError:
            return {"type": "github_repo", "confidence": 0.7, "suggested_tool": "ingest_github_repo"}

    # OpenAPI / Swagger spec
    if any(h in lowered for h in _OPENAPI_HINTS) or lowered.endswith((".json", ".yaml", ".yml")) and "api" in lowered:
        return {"type": "openapi_spec", "confidence": 0.85, "suggested_tool": "fetch_openapi_spec"}

    # GraphQL endpoint
    if any(h in lowered for h in _GRAPHQL_HINTS):
        return {"type": "graphql_endpoint", "confidence": 0.8, "suggested_tool": "fetch_graphql_schema"}

    # Documentation site
    if any(h in lowered for h in _DOCS_HINTS):
        return {"type": "docs_site", "confidence": 0.8, "suggested_tool": "scrape_docs_site"}

    # Blog / article
    if any(h in lowered for h in _BLOG_HINTS):
        return {"type": "blog_post", "confidence": 0.75, "suggested_tool": "fetch_page_knowledge"}

    # Fallback
    return {"type": "generic_page", "confidence": 0.5, "suggested_tool": "fetch_page_knowledge"}


# ---------------------------------------------------------------------------
# Tool: summarize_for_context
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,6}\s+.+", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```")


def _split_blocks(content: str) -> list[str]:
    """
    Split content into logical blocks, keeping fenced code blocks intact.
    """
    blocks: list[str] = []
    in_code = False
    buffer: list[str] = []

    for line in content.splitlines():
        if line.strip().startswith("```"):
            # Toggle code fence; keep the fence line in the current buffer
            buffer.append(line)
            if in_code:
                # closing fence → flush the whole code block as one unit
                blocks.append("\n".join(buffer))
                buffer = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            buffer.append(line)
            continue

        # Outside code: blank line is a block separator
        if line.strip() == "":
            if buffer:
                blocks.append("\n".join(buffer))
                buffer = []
        else:
            buffer.append(line)

    if buffer:
        blocks.append("\n".join(buffer))

    return [b for b in blocks if b.strip()]


def _block_priority(block: str) -> int:
    """
    Score a block for retention priority. Higher = keep first.
      headings           → 3
      code blocks        → 2
      normal paragraphs  → 1
    """
    stripped = block.strip()
    if _HEADING_RE.match(stripped):
        return 3
    if stripped.startswith("```"):
        return 2
    return 1


def summarize_for_context(content: str, target_length: int = 2000) -> dict:
    """
    Compresses raw extracted content to a target character budget while
    preserving headings and code blocks and dropping boilerplate/repetition.

    Returns:
      { original_length, summary_length, compression_ratio, content }
    """
    if not content or not content.strip():
        return {
            "original_length": 0,
            "summary_length": 0,
            "compression_ratio": 0.0,
            "content": "",
        }

    original_length = len(content)

    # Already within budget — return as-is
    if original_length <= target_length:
        return {
            "original_length": original_length,
            "summary_length": original_length,
            "compression_ratio": 1.0,
            "content": content.strip(),
        }

    blocks = _split_blocks(content)

    # De-duplicate identical/near-identical blocks (common nav/boilerplate repetition)
    seen: set[str] = set()
    unique_blocks: list[str] = []
    for b in blocks:
        key = re.sub(r"\s+", " ", b.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        unique_blocks.append(b)

    # Keep original order but prefer high-priority blocks when trimming.
    # Strategy: greedily add blocks in order; if over budget, drop lowest-priority
    # trailing paragraphs first.
    indexed = list(enumerate(unique_blocks))
    # Sort a *copy* by (priority desc, original order) to decide what to keep
    keep_order = sorted(indexed, key=lambda t: (-_block_priority(t[1]), t[0]))

    selected: list[tuple[int, str]] = []
    running = 0
    for idx, block in keep_order:
        block_len = len(block) + 2  # +2 for the join separator
        if running + block_len > target_length:
            # Try to include a truncated version of a heading/code block if it's high value
            if _block_priority(block) >= 2 and running < target_length:
                remaining = target_length - running
                if remaining > 50:
                    selected.append((idx, block[:remaining]))
                    running += remaining
            continue
        selected.append((idx, block))
        running += block_len

    # Restore original document order
    selected.sort(key=lambda t: t[0])
    summary = "\n\n".join(b for _, b in selected).strip()

    # Hard cap just in case
    if len(summary) > target_length:
        summary = summary[:target_length].rstrip() + " …"

    return {
        "original_length": original_length,
        "summary_length": len(summary),
        "compression_ratio": round(len(summary) / original_length, 3),
        "content": summary,
    }


# ---------------------------------------------------------------------------
# Tool: build_context_bundle
# ---------------------------------------------------------------------------

def _ingest_source(source: str) -> dict:
    """
    Route a single source to the correct ingestion tool based on its detected type.
    Returns { source, type, title, content } — content is always a string.
    """
    # A non-URL string is treated as a search query
    if not re.match(r"^https?://", source) and "github.com" not in source and "/" not in source:
        results = search_web(source, max_results=3)
        if results and "error" in results[0]:
            return {"source": source, "type": "search", "title": source, "content": f"[search error: {results[0]['error']}]"}
        lines = []
        for r in results:
            lines.append(f"### {r.get('title', '')}\n{r.get('url', '')}\n{r.get('snippet', '')}")
        return {"source": source, "type": "search", "title": f"Search: {source}", "content": "\n\n".join(lines)}

    detected = detect_content_type(source)
    ctype = detected["type"]

    try:
        if ctype == "github_repo":
            files = ingest_github_repo(source, max_files=10)
            if files and "error" in files[0]:
                content = f"[error: {files[0]['error']}]"
            else:
                parts = [f"### {f['path']}\n```{f.get('language', '')}\n{f.get('content', '')}\n```" for f in files if f.get("content")]
                content = "\n\n".join(parts)
            return {"source": source, "type": ctype, "title": source, "content": content}

        if ctype == "pdf":
            res = fetch_pdf_content(source)
            return {"source": source, "type": ctype, "title": source, "content": res.get("content", res.get("error", ""))}

        if ctype == "openapi_spec":
            res = fetch_openapi_spec(source)
            if "error" in res:
                return {"source": source, "type": ctype, "title": source, "content": f"[error: {res['error']}]"}
            eps = "\n".join(f"- {e['method']} {e['path']} — {e.get('summary', '')}" for e in res.get("endpoints", []))
            content = f"# {res.get('title', 'API')} (v{res.get('version', '?')})\nBase: {res.get('base_url', '')}\n\n{eps}"
            return {"source": source, "type": ctype, "title": res.get("title", source), "content": content}

        if ctype == "graphql_endpoint":
            res = fetch_graphql_schema(source)
            if "error" in res:
                return {"source": source, "type": ctype, "title": source, "content": f"[error: {res['error']}]"}
            q = ", ".join(f["name"] for f in res.get("queries", []))
            m = ", ".join(f["name"] for f in res.get("mutations", []))
            content = f"GraphQL schema\nQueries: {q}\nMutations: {m}\nTypes: {res.get('type_count', 0)}"
            return {"source": source, "type": ctype, "title": "GraphQL", "content": content}

        if ctype == "docs_site":
            pages = scrape_docs_site(source, max_pages=5)
            if pages and "error" in pages[0]:
                return {"source": source, "type": ctype, "title": source, "content": f"[error: {pages[0]['error']}]"}
            parts = [f"## {p.get('title', '')}\n{p.get('content_markdown', '')}" for p in pages if p.get("content_markdown")]
            return {"source": source, "type": ctype, "title": source, "content": "\n\n".join(parts)}

        # blog_post / generic_page → single page fetch
        res = fetch_page_knowledge(source)
        if "error" in res:
            return {"source": source, "type": ctype, "title": source, "content": f"[error: {res['error']}]"}
        return {"source": source, "type": ctype, "title": res.get("title", source), "content": res.get("content", "")}

    except Exception as e:
        return {"source": source, "type": ctype, "title": source, "content": f"[ingestion error: {str(e)}]"}


def _score_relevance(text: str, topic: str) -> float:
    """
    Cheap lexical relevance score of a chunk against a topic (no embeddings).
    Fraction of unique topic terms present in the chunk, boosted by frequency.
    """
    if not topic.strip():
        return 1.0
    topic_terms = {t for t in re.findall(r"\w+", topic.lower()) if len(t) > 2}
    if not topic_terms:
        return 1.0
    text_lower = text.lower()
    hits = sum(1 for t in topic_terms if t in text_lower)
    coverage = hits / len(topic_terms)
    # Frequency boost (capped)
    freq = sum(text_lower.count(t) for t in topic_terms)
    freq_boost = min(freq / (len(topic_terms) * 5), 0.5)
    return round(min(coverage + freq_boost, 1.0), 3)


def _chunk_text(text: str, chunk_size: int = 800) -> list[str]:
    """Split text into paragraph-aligned chunks of roughly chunk_size chars."""
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        if len(buffer) + len(para) + 2 > chunk_size and buffer:
            chunks.append(buffer.strip())
            buffer = para
        else:
            buffer = f"{buffer}\n\n{para}" if buffer else para
    if buffer.strip():
        chunks.append(buffer.strip())
    return chunks


def build_context_bundle(sources: list[str], topic: str, max_tokens: int = 4000) -> dict:
    """
    Orchestrates fetching across multiple sources (URLs, repo URLs, or search
    queries), routing each to the correct ingestion tool, then chunks, ranks by
    relevance to `topic`, and assembles a single ready-to-inject context block
    within the budget.

    `max_tokens` is treated as an approximate budget; ~4 chars per token is
    assumed for the character budget.

    Returns:
      { topic, source_count, chunk_count, char_count, approx_tokens, sources_summary, content }
    """
    char_budget = max_tokens * 4

    if not sources:
        return {
            "topic": topic,
            "source_count": 0,
            "chunk_count": 0,
            "char_count": 0,
            "approx_tokens": 0,
            "sources_summary": [],
            "content": "",
        }

    # 1. Ingest every source
    ingested = [_ingest_source(s) for s in sources]
    sources_summary = [{"source": i["source"], "type": i["type"], "title": i["title"]} for i in ingested]

    # 2. Chunk + score each chunk
    scored_chunks: list[tuple[float, str, str]] = []  # (score, source, chunk)
    for item in ingested:
        content = item.get("content") or ""
        if not content.strip():
            continue
        for chunk in _chunk_text(content):
            score = _score_relevance(chunk, topic)
            scored_chunks.append((score, item["source"], chunk))

    # 3. Rank by relevance (desc), then assemble within budget
    scored_chunks.sort(key=lambda t: t[0], reverse=True)

    assembled: list[str] = []
    running = 0
    used = 0
    for score, source, chunk in scored_chunks:
        header = f"\n\n<!-- source: {source} (relevance {score}) -->\n"
        piece = header + chunk
        if running + len(piece) > char_budget:
            continue
        assembled.append(piece)
        running += len(piece)
        used += 1

    content = "".join(assembled).strip()

    return {
        "topic": topic,
        "source_count": len(sources),
        "chunk_count": used,
        "char_count": len(content),
        "approx_tokens": len(content) // 4,
        "sources_summary": sources_summary,
        "content": content or "No relevant content could be assembled from the given sources.",
    }
