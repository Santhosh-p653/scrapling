import io

import requests

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


# ---------------------------------------------------------------------------
# Tool: fetch_pdf_content
# ---------------------------------------------------------------------------

def fetch_pdf_content(url: str, max_length: int = 10000) -> dict:
    """
    Downloads a PDF from a URL and extracts its text content, ready for
    chunking/ingestion.

    Returns:
      { url, page_count, char_count, content }  on success
      { error }                                 on failure
    """
    if not PYPDF_AVAILABLE:
        return {"error": "pypdf is not installed. Install with: pip install pypdf>=4.0.0"}

    # Download the PDF bytes
    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Failed to download PDF: {str(e)}"}

    content_type = resp.headers.get("Content-Type", "").lower()
    raw_bytes = resp.content

    # Light sanity check — some servers mislabel, so only warn via error if clearly not a PDF
    if "pdf" not in content_type and not raw_bytes[:5].startswith(b"%PDF"):
        return {"error": f"URL does not appear to be a PDF (Content-Type: {content_type or 'unknown'})"}

    # Parse the PDF
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
    except Exception as e:
        return {"error": f"Failed to parse PDF: {str(e)}"}

    # Handle encrypted PDFs — try empty-password decrypt
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            return {"error": "PDF is encrypted and could not be decrypted"}

    # Extract text page by page
    text_parts: list[str] = []
    try:
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text.strip())
    except Exception as e:
        return {"error": f"Failed to extract text from PDF: {str(e)}"}

    full_text = "\n\n".join(text_parts)

    if not full_text.strip():
        return {
            "url": url,
            "page_count": len(reader.pages),
            "char_count": 0,
            "content": "No extractable text found (PDF may be scanned/image-only).",
        }

    truncated = False
    if len(full_text) > max_length:
        full_text = full_text[:max_length] + f"\n\n[... Truncated to fit token budget (max: {max_length} chars)]"
        truncated = True

    return {
        "url": url,
        "page_count": len(reader.pages),
        "char_count": len(full_text),
        "truncated": truncated,
        "content": full_text,
    }
