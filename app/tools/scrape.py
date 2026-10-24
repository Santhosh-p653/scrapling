from scrapling.fetchers import Fetcher, StealthyFetcher
from markdownify import markdownify as md


def fetch_page_knowledge(url: str, max_length: int = 6000) -> dict:
    """
    Ultra-fast web content and knowledge extractor using Scrapling's high-speed HTTP engine.
    Extracts page title, metadata, main text, and clean LLM-ready markdown.
    """
    try:
        fetcher = Fetcher(auto_match=False)
        page = fetcher.get(url, stealthy_headers=True)

        if not page or page.status >= 400:
            return {"error": f"Failed to fetch page. HTTP Status: {page.status if page else 'Unknown'}"}

        title = page.css("title::text").get() or "No title"

        main_content = (
            page.css("article").get() or
            page.css("main").get() or
            page.css("#content").get() or
            page.css("body").get() or ""
        )

        clean_markdown = md(main_content, heading_style="ATX", strip=["script", "style", "nav", "footer", "aside"])
        lines = [line.strip() for line in clean_markdown.splitlines() if line.strip()]
        formatted_output = "\n\n".join(lines)

        if len(formatted_output) > max_length:
            formatted_output = formatted_output[:max_length] + f"\n\n[... Truncated to fit token budget (max: {max_length} chars)]"

        return {
            "title": title,
            "url": url,
            "char_count": len(formatted_output),
            "content": formatted_output or "No text could be extracted."
        }
    except Exception as e:
        return {"error": f"Scrapling extraction error: {str(e)}"}


def fetch_stealth_knowledge(url: str, max_length: int = 6000) -> dict:
    """
    Bypasses aggressive anti-bot protections (Cloudflare, Akamai, PerimeterX)
    using Scrapling's StealthyFetcher engine with real browser fingerprinting.
    """
    try:
        page = StealthyFetcher.fetch(url, headless=True, network_idle=True)

        title = page.css("title::text").get() or "No title"
        main_content = page.css("article").get() or page.css("main").get() or page.css("body").get() or ""

        clean_markdown = md(main_content, heading_style="ATX", strip=["script", "style", "nav", "footer", "aside"])
        lines = [line.strip() for line in clean_markdown.splitlines() if line.strip()]
        formatted_output = "\n\n".join(lines)

        if len(formatted_output) > max_length:
            formatted_output = formatted_output[:max_length] + "\n\n[... Truncated]"

        return {
            "title": title,
            "url": url,
            "mode": "stealth",
            "content": formatted_output or "No text could be extracted."
        }
    except Exception as e:
        return {"error": f"Stealth extraction error: {str(e)}"}


def batch_knowledge_extract(urls: list[str]) -> list[dict]:
    """
    Extracts structured content from multiple URLs in a single call for comparative RAG and synthesis.
    Accepts up to 5 URLs per call.
    """
    results = []
    fetcher = Fetcher(auto_match=False)
    for target in urls[:5]:
        try:
            page = fetcher.get(target, stealthy_headers=True)
            title = page.css("title::text").get() or "No title"
            content = page.css("article").get() or page.css("main").get() or page.css("body").get() or ""
            clean = md(content, heading_style="ATX", strip=["script", "style", "nav", "footer"])
            results.append({
                "url": target,
                "title": title,
                "summary_content": clean[:2000]
            })
        except Exception as e:
            results.append({"url": target, "error": str(e)})
    return results
