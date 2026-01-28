"""
DRS (Dynamic Regulatory System) API integration.

Provides access to FAA Advisory Circulars and other regulatory documents.

Implements cache-first pattern for fetch_drs_document:
1. Check blob storage cache
2. If cached: return content, schedule background indexing (on first hit)
3. If not cached: fetch from API, store in cache, return content
"""

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.cache import get_cache, DocumentCache
from app.services.indexer import schedule_indexing

logger = logging.getLogger(__name__)


async def search_drs(
    keywords: list[str],
    doc_type: str = "AC",
    status_filter: list[str] | None = None,
    max_results: int = 10,
) -> str:
    """
    Search DRS for FAA documents by keywords.
    
    Args:
        keywords: List of keywords to search for
        doc_type: Document type (AC, AD, TSO, Order, etc.)
        status_filter: Status filter (default: ["Current"])
        max_results: Maximum results to return
    
    Returns:
        Formatted search results.
    """
    settings = get_settings()
    base_url = settings.drs_api_base_url
    api_key = settings.drs_api_key
    
    if not api_key:
        return "Error: DRS_API_KEY not configured"
    
    if status_filter is None:
        status_filter = ["Current"]
    
    url = f"{base_url}/data-pull/{doc_type}/filtered"
    
    logger.info(f"DRS search: keywords={keywords}, type={doc_type}, status={status_filter}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "offset": 0,
                    "documentFilters": {
                        "drs:status": status_filter,
                        "Keyword": keywords[:10],  # Max 10 keywords
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(f"DRS HTTP error: {e}")
            return f"DRS search error: HTTP {e.response.status_code}"
        except Exception as e:
            logger.error(f"DRS error: {e}")
            return f"DRS search error: {e}"
    
    documents = data.get("documents", [])
    
    if not documents:
        return f"No DRS documents found for keywords: {keywords}"
    
    # Format results
    formatted = [f"## DRS Search Results\n**Keywords:** {', '.join(keywords)}\n**Type:** {doc_type}\n"]
    
    for i, doc in enumerate(documents[:max_results], 1):
        doc_number = doc.get("drs:documentNumber", "Unknown")
        title = doc.get("drs:title", doc_number)
        status = doc.get("drs:status", "")
        guid = doc.get("documentGuid", "")
        
        formatted.append(f"### {i}. {doc_number}")
        formatted.append(f"**Title:** {title}")
        if status:
            formatted.append(f"**Status:** {status}")
        if guid:
            formatted.append(f"**GUID:** {guid}")
        formatted.append("")
    
    total = data.get("summary", {}).get("totalItems", len(documents))
    formatted.append(f"\n*Showing {min(max_results, len(documents))} of {total} results*")
    
    return "\n".join(formatted)


async def fetch_drs_document(
    doc_number: str,
    doc_type: str = "AC",
    index_name: str | None = None,
) -> str:
    """
    Fetch a specific DRS document by document number.
    
    Uses cache-first pattern:
    1. Check blob cache for existing content
    2. On cache hit: return content + schedule indexing if not already indexed
    3. On cache miss: fetch from DRS, cache the result, return content
    
    Args:
        doc_number: Document number (e.g., "AC 25.1309-1A")
        doc_type: Document type (AC, AD, TSO, Order, etc.)
        index_name: Optional search index name (injected by orchestrator)
    
    Returns:
        Document content or error message.
    """
    settings = get_settings()
    base_url = settings.drs_api_base_url
    api_key = settings.drs_api_key
    
    if not api_key:
        return "Error: DRS_API_KEY not configured"
    
    logger.info(f"DRS fetch: {doc_type}/{doc_number}")
    
    # Generate cache key
    cache_key = DocumentCache.drs_key(doc_type, doc_number)
    
    # Check cache first (if enabled)
    if settings.cache_enabled:
        try:
            cache = get_cache()
            cached = await cache.get(cache_key)
            
            if cached:
                logger.info(f"Cache hit for DRS {doc_type}/{doc_number}")
                
                # Schedule indexing on first cache hit (not already indexed)
                if not cached.indexed and settings.auto_index_on_cache_hit:
                    schedule_indexing(
                        content=cached.content,
                        doc_type="drs",
                        doc_id=cached.doc_id,
                        title=cached.title or f"{doc_type} {doc_number}",
                        source_url=f"https://drs.faa.gov/browse/FSIMS/doctypeDetails?docType={doc_type}",
                        cache_key=cache_key,
                        index_name=index_name,
                    )
                
                return cached.content
        except Exception as e:
            logger.warning(f"Cache lookup failed, falling back to API: {e}")
    
    # Cache miss - fetch from DRS API
    url = f"{base_url}/data-pull/{doc_type}/filtered"
    
    # Keep client open for both search and download
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Search by keyword (document number)
            response = await client.post(
                url,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "offset": 0,
                    "documentFilters": {
                        "drs:status": ["Current"],
                        "Keyword": [doc_number],
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(f"DRS HTTP error: {e}")
            return f"DRS fetch error: HTTP {e.response.status_code}"
        except Exception as e:
            logger.error(f"DRS error: {e}")
            return f"DRS fetch error: {e}"
        
        documents = data.get("documents", [])
        
        if not documents:
            return f"Document not found: {doc_type}/{doc_number}"
        
        # Find best match
        normalized_input = _normalize_doc_number(doc_number)
        
        best_match = None
        for doc in documents:
            doc_num = doc.get("drs:documentNumber", "")
            normalized_doc = _normalize_doc_number(doc_num)
            
            # Exact match
            if normalized_doc == normalized_input:
                best_match = doc
                break
            
            # Base number match (ignore CHG, Ed Update suffixes)
            if _get_base_doc_number(normalized_doc) == _get_base_doc_number(normalized_input):
                best_match = doc
                break
            
            # Prefix match
            if normalized_doc.startswith(normalized_input) or normalized_input.startswith(_get_base_doc_number(normalized_doc)):
                best_match = doc
        
        if not best_match:
            # Fall back to first result
            best_match = documents[0]
            logger.warning(f"No exact match for {doc_number}, using: {best_match.get('drs:documentNumber')}")
        
        # Get document details
        doc_number_found = best_match.get("drs:documentNumber", "Unknown")
        title = best_match.get("drs:title", doc_number_found)
        status = best_match.get("drs:status", "")
        download_url = best_match.get("mainDocumentDownloadURL", "")
        guid = best_match.get("documentGuid", "")
        
        # Format response with metadata
        result = [
            f"## {doc_type} {doc_number_found}",
            f"**Title:** {title}",
        ]
        
        if status:
            result.append(f"**Status:** {status}")
        
        if download_url:
            # Try to fetch PDF and extract text (client still open)
            text = await _download_and_extract_pdf(download_url, api_key, client)
            if text:
                # Truncate if too long
                if len(text) > 15000:
                    text = text[:15000] + "\n\n[... Document truncated. Full document is larger.]"
                result.append(f"\n### Document Content\n\n{text}")
            else:
                result.append(f"\n**Download URL available:** Yes (GUID: {guid})")
                result.append("\n*Could not extract text from PDF automatically.*")
        else:
            result.append("\n*No download URL available for this document.*")
        
        full_content = "\n".join(result)
        
        # Store in cache (if enabled)
        if settings.cache_enabled:
            try:
                cache = get_cache()
                doc_id = f"{doc_type}-{_normalize_doc_number(doc_number_found).replace(' ', '-')}"
                await cache.put(
                    key=cache_key,
                    content=full_content,
                    doc_type="drs",
                    doc_id=doc_id,
                    title=title,
                    metadata={
                        "doc_type": doc_type,
                        "doc_number": doc_number_found,
                        "status": status,
                        "guid": guid,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to cache DRS document: {e}")
        
        return full_content


async def _download_and_extract_pdf(
    download_url: str,
    api_key: str,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Download PDF and extract text."""
    try:
        # Use provided client or create new one
        if client is None:
            async with httpx.AsyncClient(timeout=60.0) as new_client:
                return await _do_download_and_extract(download_url, api_key, new_client)
        else:
            return await _do_download_and_extract(download_url, api_key, client)
    except Exception as e:
        logger.error(f"PDF download/extract error: {e}")
        return None


async def _do_download_and_extract(
    download_url: str,
    api_key: str,
    client: httpx.AsyncClient,
) -> str | None:
    """Actually download and extract PDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not installed, cannot extract PDF text")
        return None
    
    logger.info(f"Downloading PDF from DRS: {download_url[:80]}...")
    
    response = await client.get(
        download_url,
        headers={"x-api-key": api_key},
        follow_redirects=True,
    )
    response.raise_for_status()
    
    pdf_bytes = response.content
    logger.info(f"Downloaded {len(pdf_bytes) / 1024:.1f} KB")
    
    # Extract text using PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_parts = []
    num_pages = len(doc)
    
    for page_num in range(num_pages):
        page = doc.load_page(page_num)
        text_parts.append(page.get_text())
    
    doc.close()
    
    text = "\n\n".join(text_parts)
    logger.info(f"Extracted {len(text)} characters from {num_pages} pages")
    
    return text.strip() if text.strip() else None


def _normalize_doc_number(doc_num: str) -> str:
    """Normalize document number for comparison."""
    import re
    normalized = doc_num.upper().strip()
    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    # Ensure space after type prefix
    normalized = re.sub(r'^(AC|AD|TSO|ORDER)\s*', r'\1 ', normalized)
    return normalized


def _get_base_doc_number(doc_num: str) -> str:
    """Get base document number without CHG/Ed Update suffixes."""
    import re
    normalized = _normalize_doc_number(doc_num)
    # Remove CHG #, Ed Update, etc.
    normalized = re.sub(r'\s+(CHG|CHANGE)\s*\d*$', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\s+Ed\s+Update\s*\d*$', '', normalized, flags=re.IGNORECASE)
    return normalized.strip()


# Tool definitions for Claude API
SEARCH_DRS_DEFINITION = {
    "name": "search_drs",
    "description": """Search the FAA Dynamic Regulatory System (DRS) for Advisory Circulars and other regulatory documents.

Use this tool when:
- Looking for Advisory Circulars (ACs) on a topic
- Searching for FAA guidance documents
- Finding documents that are NOT in the indexed content
- User specifically asks about ACs or guidance material

Document types:
- AC: Advisory Circulars (most common)
- AD: Airworthiness Directives
- TSO: Technical Standard Orders
- Order: FAA Orders

The search uses keywords to find relevant documents. Results include document numbers and titles.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords to search for (e.g., ['HIRF', 'protection'] or ['system safety', 'assessment'])",
            },
            "doc_type": {
                "type": "string",
                "description": "Document type to search",
                "enum": ["AC", "AD", "TSO", "Order"],
                "default": "AC",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 10)",
                "default": 10,
            },
        },
        "required": ["keywords"],
    },
}

FETCH_DRS_DOCUMENT_DEFINITION = {
    "name": "fetch_drs_document",
    "description": """Fetch a specific FAA document from DRS by its document number.

Use this tool when:
- You know the specific document number (e.g., "AC 25.1309-1A")
- You found a document in search results and want the full content
- User asks for a specific Advisory Circular

This downloads the PDF and extracts the text content.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "doc_number": {
                "type": "string",
                "description": "Document number (e.g., 'AC 25.1309-1A', 'AC 23-8C')",
            },
            "doc_type": {
                "type": "string",
                "description": "Document type",
                "enum": ["AC", "AD", "TSO", "Order"],
                "default": "AC",
            },
        },
        "required": ["doc_number"],
    },
}
