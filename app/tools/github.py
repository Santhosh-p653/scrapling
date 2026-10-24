import re
import requests

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_repo_url(repo_url: str) -> tuple[str, str]:
    """
    Extract owner and repo name from a GitHub URL or 'owner/repo' string.
    Raises ValueError if the URL cannot be parsed.
    """
    repo_url = repo_url.rstrip("/")
    # Handle full URLs: https://github.com/owner/repo
    match = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
    if match:
        return match.group(1), match.group(2)
    # Handle shorthand: owner/repo
    parts = repo_url.split("/")
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    raise ValueError(f"Cannot parse GitHub repo URL: {repo_url!r}")


def _gh_headers(github_token: str | None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def _detect_language(path: str) -> str:
    ext_map = {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript", ".md": "markdown",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".html": "html", ".css": "css", ".sh": "shell",
        ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
        ".cpp": "cpp", ".c": "c", ".cs": "csharp", ".tf": "terraform",
    }
    for ext, lang in ext_map.items():
        if path.endswith(ext):
            return lang
    return "plaintext"


# ---------------------------------------------------------------------------
# Tool: ingest_github_repo
# ---------------------------------------------------------------------------

def ingest_github_repo(
    repo_url: str,
    branch: str = "main",
    file_extensions: list[str] | None = None,
    max_files: int = 50,
    github_token: str | None = None,
) -> list[dict]:
    """
    Ingests a GitHub repository by fetching the full file tree and returning the
    raw content of matched files. Supports public repos; private repos via github_token.

    Returns a list of { path, language, content, char_count } dicts, or a single
    { error } dict on failure.
    """
    if file_extensions is None:
        file_extensions = [".py", ".md", ".ts", ".js"]

    try:
        owner, repo = _parse_repo_url(repo_url)
    except ValueError as e:
        return [{"error": str(e)}]

    headers = _gh_headers(github_token)
    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"

    try:
        resp = requests.get(tree_url, headers=headers, timeout=15)
        if resp.status_code == 404:
            # Try 'master' fallback if 'main' was the default and returned 404
            if branch == "main":
                resp = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo}/git/trees/master?recursive=1",
                    headers=headers,
                    timeout=15,
                )
        resp.raise_for_status()
    except requests.RequestException as e:
        return [{"error": f"GitHub API error fetching tree: {str(e)}"}]

    tree_data = resp.json()
    if "tree" not in tree_data:
        return [{"error": "GitHub returned an unexpected tree response", "detail": tree_data.get("message", "")}]

    # Filter to blobs (files) matching requested extensions
    matched = [
        item for item in tree_data["tree"]
        if item.get("type") == "blob"
        and any(item["path"].endswith(ext) for ext in file_extensions)
    ][:max_files]

    if not matched:
        return [{"error": f"No files matching {file_extensions} found in {owner}/{repo}@{branch}"}]

    results = []
    for item in matched:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{item['path']}"
        try:
            raw_resp = requests.get(raw_url, headers={"Authorization": f"Bearer {github_token}"} if github_token else {}, timeout=10)
            raw_resp.raise_for_status()
            content = raw_resp.text
        except requests.RequestException as e:
            content = None
            results.append({
                "path": item["path"],
                "language": _detect_language(item["path"]),
                "content": None,
                "char_count": 0,
                "error": f"Failed to fetch raw content: {str(e)}"
            })
            continue

        results.append({
            "path": item["path"],
            "language": _detect_language(item["path"]),
            "content": content,
            "char_count": len(content),
        })

    return results


# ---------------------------------------------------------------------------
# Tool: fetch_github_file
# ---------------------------------------------------------------------------

def fetch_github_file(
    repo_url: str,
    file_path: str,
    branch: str = "main",
    github_token: str | None = None,
) -> dict:
    """
    Fetches a single raw file from any GitHub repository.
    Returns { path, content, language } or { error }.
    """
    try:
        owner, repo = _parse_repo_url(repo_url)
    except ValueError as e:
        return {"error": str(e)}

    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
    auth_headers = {"Authorization": f"Bearer {github_token}"} if github_token else {}

    try:
        resp = requests.get(raw_url, headers=auth_headers, timeout=10)
        if resp.status_code == 404 and branch == "main":
            # Fallback to master
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/{file_path}"
            resp = requests.get(raw_url, headers=auth_headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Failed to fetch file: {str(e)}"}

    return {
        "path": file_path,
        "content": resp.text,
        "language": _detect_language(file_path),
    }


# ---------------------------------------------------------------------------
# Tool: fetch_github_issues
# ---------------------------------------------------------------------------

def fetch_github_issues(
    repo_url: str,
    state: str = "open",
    max_issues: int = 20,
    github_token: str | None = None,
) -> list[dict]:
    """
    Fetches issues from a GitHub repository including title, body, labels, and comments.
    state can be 'open', 'closed', or 'all'.
    Returns a list of issue dicts or a single { error } dict.
    """
    try:
        owner, repo = _parse_repo_url(repo_url)
    except ValueError as e:
        return [{"error": str(e)}]

    headers = _gh_headers(github_token)
    issues_url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    params = {"state": state, "per_page": min(max_issues, 100), "page": 1}

    try:
        resp = requests.get(issues_url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        return [{"error": f"GitHub API error fetching issues: {str(e)}"}]

    raw_issues = resp.json()
    if not isinstance(raw_issues, list):
        return [{"error": "Unexpected response from GitHub issues API", "detail": str(raw_issues)}]

    results = []
    for issue in raw_issues[:max_issues]:
        # Skip pull requests (GitHub returns PRs in the issues endpoint)
        if "pull_request" in issue:
            continue

        # Fetch comments if any
        comments = []
        if issue.get("comments", 0) > 0:
            try:
                c_resp = requests.get(issue["comments_url"], headers=headers, timeout=10)
                c_resp.raise_for_status()
                for c in c_resp.json():
                    comments.append({
                        "author": c.get("user", {}).get("login"),
                        "body": c.get("body", ""),
                        "created_at": c.get("created_at"),
                    })
            except requests.RequestException:
                pass  # Comments are best-effort

        results.append({
            "number": issue.get("number"),
            "title": issue.get("title"),
            "state": issue.get("state"),
            "author": issue.get("user", {}).get("login"),
            "labels": [lbl.get("name") for lbl in issue.get("labels", [])],
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "body": issue.get("body", ""),
            "comments": comments,
            "url": issue.get("html_url"),
        })

    return results


# ---------------------------------------------------------------------------
# Tool: search_github_code
# ---------------------------------------------------------------------------

def search_github_code(
    query: str,
    repo: str | None = None,
    language: str | None = None,
    max_results: int = 10,
    github_token: str | None = None,
) -> list[dict]:
    """
    Searches GitHub code using the GitHub code search API.
    Returns matching file snippets with repo, path, and a raw content preview.

    Note: GitHub code search requires authentication for reliable results.
    Pass a github_token for best results.
    """
    headers = _gh_headers(github_token)

    # Build search query
    search_q = query
    if repo:
        # Accept both full URL and 'owner/repo' shorthand
        try:
            owner, repo_name = _parse_repo_url(repo)
            search_q += f" repo:{owner}/{repo_name}"
        except ValueError:
            search_q += f" repo:{repo}"
    if language:
        search_q += f" language:{language}"

    params = {"q": search_q, "per_page": min(max_results, 30)}

    try:
        resp = requests.get(
            "https://api.github.com/search/code",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return [{"error": f"GitHub code search error: {str(e)}"}]

    data = resp.json()
    items = data.get("items", [])

    results = []
    for item in items[:max_results]:
        # Fetch a preview of the raw file (first 2000 chars)
        raw_url = item.get("git_url", "").replace("api.github.com/repos", "raw.githubusercontent.com").replace("/git/blobs/", "/")
        # Use the html_url to derive the raw URL more reliably
        html_url = item.get("html_url", "")
        raw_preview = None
        if html_url:
            raw_url = html_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            try:
                auth_h = {"Authorization": f"Bearer {github_token}"} if github_token else {}
                raw_resp = requests.get(raw_url, headers=auth_h, timeout=8)
                if raw_resp.status_code == 200:
                    raw_preview = raw_resp.text[:2000]
            except requests.RequestException:
                pass

        results.append({
            "repo": item.get("repository", {}).get("full_name"),
            "path": item.get("path"),
            "language": _detect_language(item.get("path", "")),
            "url": html_url,
            "content_preview": raw_preview,
        })

    return results
