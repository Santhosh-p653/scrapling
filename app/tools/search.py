from duckduckgo_search import DDGS


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the live web anonymously for current events, technical docs, or real-time data.
    Returns a list of results with title, snippet, and target URL.
    """
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title"),
                    "url": r.get("href"),
                    "snippet": r.get("body")
                })
        return results
    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]
