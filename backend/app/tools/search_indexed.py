"""
Search indexed documents using the Search Proxy.

The Search Proxy enforces fingerprint-based isolation for personal documents.
All searches go through the proxy which adds the fingerprint filter.
"""

import logging
from typing import Any, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def search_indexed_content(
    query: str,
    top_k: int = 5,
    doc_type: Optional[str] = None,
    index_name: Optional[str] = None,
    fingerprint: Optional[str] = None,
) -> str:
    """
    Search indexed documents using the Search Proxy.
    
    The proxy enforces fingerprint filtering to isolate personal documents.
    Results include regulatory documents (visible to all) + user's personal documents.
    
    Args:
        query: Search query (natural language)
        top_k: Number of results to return
        doc_type: Optional filter by document type ("cfr", "ac", etc.)
        index_name: Search index (e.g., "faa-agent", "nrc-agent", "dod-agent")
        fingerprint: User's browser fingerprint (required for personal doc isolation)
    
    Returns:
        Formatted search results with citations.
    """
    settings = get_settings()
    
    # Determine index
    index = index_name or settings.azure_search_index
    
    # Require fingerprint for search
    if not fingerprint:
        logger.warning("No fingerprint provided for search, using placeholder")
        fingerprint = "anonymous-search-user"
    
    # Build request for search proxy
    search_request = {
        "query": query,
        "index": index,
        "fingerprint": fingerprint,
        "top": min(top_k, 20),  # Proxy max is 20
    }
    
    if doc_type:
        search_request["doc_type"] = doc_type
    
    logger.info(f"Proxy search: '{query}' (index={index}, fingerprint={fingerprint[:8]}...)")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{settings.search_proxy_url}/search",
                headers={"Content-Type": "application/json"},
                json=search_request,
            )
            response.raise_for_status()
            data = response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Search Proxy HTTP error: {e.response.status_code} - {e.response.text}")
            return f"Search error: HTTP {e.response.status_code}"
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to Search Proxy at {settings.search_proxy_url}: {e}")
            return "Search error: Cannot connect to search service"
        except Exception as e:
            logger.error(f"Search Proxy error: {e}")
            return f"Search error: {e}"
    
    # Format results
    results = data.get("results", [])
    
    if not results:
        return f"No results found for: {query}"
    
    formatted = [f"## Search Results for: {query}\n"]
    
    for i, doc in enumerate(results, 1):
        title = doc.get("title", "Untitled")
        citation = doc.get("citation", "")
        content = doc.get("content", "")[:500]  # Truncate for readability
        source = doc.get("source", "")
        is_personal = doc.get("owner_fingerprint") is not None
        
        formatted.append(f"### {i}. {title}")
        if citation:
            formatted.append(f"**Citation:** {citation}")
        if source:
            formatted.append(f"**Source:** {source}")
        if is_personal:
            formatted.append("**[Personal Document]**")
        formatted.append(f"\n{content}...")
        formatted.append("")
    
    return "\n".join(formatted)


# Tool definition for Claude API
TOOL_DEFINITION = {
    "name": "search_indexed_content",
    "description": """Search the indexed documents (CFR sections, Advisory Circulars, personal uploads, etc.) for relevant information.

Use this tool FIRST when answering questions about regulations. It searches the pre-indexed knowledge base for relevant content, including any documents the user has uploaded.

When to use:
- User asks a general question about certification
- Looking for relevant regulations on a topic
- Finding Advisory Circulars related to a requirement
- Before fetching specific CFR sections (to find which ones are relevant)
- User asks about their uploaded documents

The search returns document snippets with citations. Results may include:
- Regulatory documents (CFR, ACs, etc.) - visible to all users
- Personal documents - only visible to the user who uploaded them

If you need the complete text of a specific section found in results, use fetch_cfr_section.
""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query (e.g., 'HIRF protection requirements' or 'lightning strike certification')",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5, max: 20)",
                "default": 5,
            },
            "doc_type": {
                "type": "string",
                "description": "Optional: filter by document type",
                "enum": ["cfr", "ac", "order", "policy", "user_upload"],
            },
        },
        "required": ["query"],
    },
}
