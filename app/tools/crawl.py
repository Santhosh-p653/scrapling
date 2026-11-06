import re
from urllib.parse import urljoin, urlparse, urldefrag
from collections import deque

import requests
from scrapling.fetchers import Fetcher
from markdownify import markdownify as md

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_markdown(html: str, max_length: int | None = None) -> str:
    """Convert HTML to clean LLM markdown, stripping nav/footer/sidebar noise."""
    if not html:
        return ""
    clean = md(html, heading_style="ATX", strip=["script", "style", "nav", "footer", "aside"])
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    out = "\n\n".join(lines)
    if max_length is not None and len(out) > max_length:
        out = out[:max_length] + f"\n\n[... Truncated to fit token budget (max: {max_length} chars)]"
    return out


def _extract_main_html(page) -> str:
    """Pull the most relevant content container from a Scrapling page."""
    return (
        page.css("article").get()
        or page.css("main").get()
        or page.css("#content").get()
        or page.css(".content").get()
        or page.css("body").get()
        or ""
    )


def _same_domain(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc == urlparse(url_b).netloc


def _normalize_link(base_url: str, href: str) -> str | None:
    """Resolve a relative href against base_url, drop fragments, skip non-http links."""
    if not href:
        return None
    href = href.strip()
    # Skip mailto/javascript/anchors/etc.
    if href.startswith(("mailto:", "javascript:", "tel:", "#")):
        return None
    absolute = urljoin(base_url, href)
    absolute, _ = urldefrag(absolute)  # strip #fragment
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return None
    return absolute


def _extract_links(page, base_url: str) -> list[str]:
    """Extract all normalized outbound links from a Scrapling page."""
    links = []
    try:
        hrefs = page.css("a::attr(href)").getall()
    except Exception:
        hrefs = []
    for href in hrefs:
        normalized = _normalize_link(base_url, href)
        if normalized:
            links.append(normalized)
    return links


# ---------------------------------------------------------------------------
# Tool: scrape_docs_site
# ---------------------------------------------------------------------------

def scrape_docs_site(
    start_url: str,
    max_pages: int = 20,
    same_domain_only: bool = True,
    max_length_per_page: int = 6000,
) -> list[dict]:
    """
    Crawls a documentation site starting from start_url, following internal links
    breadth-first up to max_pages. Returns clean markdown per page.

    Returns a list of { url, title, content_markdown } dicts, or a single
    { error } dict if the start page cannot be fetched.
    """
    fetcher = Fetcher(auto_match=False)
    visited: set[str] = set()
    queue: deque[str] = deque([start_url])
    results: list[dict] = []

    start_netloc = urlparse(start_url).netloc

    while queue and len(results) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        try:
            page = fetcher.get(url, stealthy_headers=True)
        except Exception as e:
            # Record the failure but keep crawling other pages
            if url == start_url:
                return [{"error": f"Failed to fetch start page {start_url}: {str(e)}"}]
            results.append({"url": url, "error": str(e)})
            continue

        if not page or page.status >= 400:
            if url == start_url:
                status = page.status if page else "Unknown"
                return [{"error": f"Failed to fetch start page. HTTP Status: {status}"}]
            continue

        title = page.css("title::text").get() or "No title"
        main_html = _extract_main_html(page)
        content_markdown = _clean_markdown(main_html, max_length_per_page)

        results.append({
            "url": url,
            "title": title,
            "content_markdown": content_markdown or "No text could be extracted.",
        })

        # Enqueue new internal links
        for link in _extract_links(page, url):
            if link in visited:
                continue
            if same_domain_only and urlparse(link).netloc != start_netloc:
                continue
            queue.append(link)

    return results


# ---------------------------------------------------------------------------
# Tool: scrape_sitemap
# ---------------------------------------------------------------------------

def _parse_sitemap_xml(xml_text: str) -> tuple[list[str], list[str]]:
    """
    Parse sitemap XML. Returns (page_urls, nested_sitemap_urls).
    Handles both urlset (regular sitemaps) and sitemapindex (index files).
    """
    page_urls: list[str] = []
    nested_sitemaps: list[str] = []

    if BS4_AVAILABLE:
        soup = BeautifulSoup(xml_text, "xml")
        # sitemapindex → nested sitemaps
        for sm in soup.find_all("sitemap"):
            loc = sm.find("loc")
            if loc and loc.text:
                nested_sitemaps.append(loc.text.strip())
        # urlset → page URLs
        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            if loc and loc.text:
                page_urls.append(loc.text.strip())
    else:
        # Regex fallback if bs4/lxml not installed
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", xml_text, re.IGNORECASE | re.DOTALL)
        if "<sitemapindex" in xml_text.lower():
            nested_sitemaps = [l.strip() for l in locs]
        else:
            page_urls = [l.strip() for l in locs]

    return page_urls, nested_sitemaps


def scrape_sitemap(
    sitemap_url: str,
    max_urls: int = 50,
    max_length_per_page: int = 4000,
) -> list[dict]:
    """
    Parses a sitemap.xml (including nested sitemap index files), then batch-fetches
    each page and returns clean markdown.

    Returns a list of { url, title, content_markdown } dicts, or a single
    { error } dict if the sitemap cannot be fetched/parsed.
    """
    # Collect all page URLs, resolving one level of sitemap-index nesting
    collected_urls: list[str] = []
    sitemaps_to_process: deque[str] = deque([sitemap_url])
    processed_sitemaps: set[str] = set()

    while sitemaps_to_process and len(collected_urls) < max_urls:
        current = sitemaps_to_process.popleft()
        if current in processed_sitemaps:
            continue
        processed_sitemaps.add(current)

        try:
            resp = requests.get(current, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            if current == sitemap_url:
                return [{"error": f"Failed to fetch sitemap: {str(e)}"}]
            continue

        page_urls, nested = _parse_sitemap_xml(resp.text)
        collected_urls.extend(page_urls)
        for n in nested:
            if n not in processed_sitemaps:
                sitemaps_to_process.append(n)

    collected_urls = collected_urls[:max_urls]

    if not collected_urls:
        return [{"error": f"No page URLs found in sitemap: {sitemap_url}"}]

    # Batch-fetch each page
    fetcher = Fetcher(auto_match=False)
    results: list[dict] = []
    for url in collected_urls:
        try:
            page = fetcher.get(url, stealthy_headers=True)
            if not page or page.status >= 400:
                results.append({"url": url, "error": f"HTTP {page.status if page else 'Unknown'}"})
                continue
            title = page.css("title::text").get() or "No title"
            main_html = _extract_main_html(page)
            content_markdown = _clean_markdown(main_html, max_length_per_page)
            results.append({
                "url": url,
                "title": title,
                "content_markdown": content_markdown or "No text could be extracted.",
            })
        except Exception as e:
            results.append({"url": url, "error": str(e)})

    return results
