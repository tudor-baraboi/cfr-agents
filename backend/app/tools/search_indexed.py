"""
Search indexed FAA documents using Azure AI Search.

Uses hybrid search (keyword + vector) for best results.
"""

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def generate_query_embedding(query: str) -> list[float] | None:
    """Generate embedding for search query using Azure AI Services Cohere model."""
    settings = get_settings()
    
    if not settings.azure_ai_services_endpoint or not settings.azure_ai_services_key:
        logger.warning("Azure AI Services not configured, falling back to keyword search")
        return None
    
    # Azure AI Model Inference API format for Cohere
    url = f"{settings.azure_ai_services_endpoint}/models/embeddings?api-version=2024-05-01-preview"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.azure_ai_services_key}",
                    "Content-Type": "application/json",
                    "extra-parameters": "pass-through",
                },
                json={
                    "input": [query[:8000]],
                    "model": settings.azure_ai_services_embedding_deployment,
                    "input_type": "query",  # Use 'query' for search queries
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.warning(f"Failed to generate query embedding: {e}")
            return None


async def search_indexed_content(
    query: str,
    top_k: int = 5,
    doc_type: str | None = None,
    index_name: str | None = None,
) -> str:
    """
    Search indexed documents using hybrid search (keyword + vector).
    
    Args:
        query: Search query (natural language)
        top_k: Number of results to return
        doc_type: Optional filter by document type ("cfr", "ac", etc.)
        index_name: Optional override for search index (defaults to settings.azure_search_index)
    
    Returns:
        Formatted search results with citations.
    """
    settings = get_settings()
    
    if not settings.azure_search_endpoint or not settings.azure_search_key:
        return "Error: Azure AI Search not configured"
    
    endpoint = settings.azure_search_endpoint
    index = index_name or settings.azure_search_index
    api_key = settings.azure_search_key
    
    url = f"{endpoint}/indexes/{index}/docs/search?api-version=2024-07-01"
    
    # Build search request
    search_body: dict[str, Any] = {
        "search": query,
        "top": top_k,
        "select": "id,title,content,source,doc_type,citation",
        "queryType": "simple",
    }
    
    # Add filter if doc_type specified
    if doc_type:
        search_body["filter"] = f"doc_type eq '{doc_type}'"
    
    # Generate embedding for hybrid search
    query_embedding = await generate_query_embedding(query)
    
    if query_embedding:
        # Use hybrid search (keyword + vector)
        search_body["vectorQueries"] = [
            {
                "kind": "vector",
                "vector": query_embedding,
                "fields": "embedding",
                "k": top_k,
            }
        ]
        logger.info(f"Hybrid search: '{query}' (top_k={top_k}, doc_type={doc_type})")
    else:
        logger.info(f"Keyword-only search: '{query}' (top_k={top_k}, doc_type={doc_type})")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": api_key,
                },
                json=search_body,
            )
            response.raise_for_status()
            data = response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Azure Search HTTP error: {e}")
            return f"Search error: HTTP {e.response.status_code}"
        except Exception as e:
            logger.error(f"Azure Search error: {e}")
            return f"Search error: {e}"
    
    # Format results
    results = data.get("value", [])
    
    if not results:
        return f"No results found for: {query}"
    
    formatted = [f"## Search Results for: {query}\n"]
    
    for i, doc in enumerate(results, 1):
        title = doc.get("title", "Untitled")
        citation = doc.get("citation", "")
        content = doc.get("content", "")[:500]  # Truncate for readability
        source = doc.get("source", "")
        
        formatted.append(f"### {i}. {title}")
        if citation:
            formatted.append(f"**Citation:** {citation}")
        if source:
            formatted.append(f"**Source:** {source}")
        formatted.append(f"\n{content}...")
        formatted.append("")
    
    return "\n".join(formatted)


# Tool definition for Claude API
TOOL_DEFINITION = {
    "name": "search_indexed_content",
    "description": """Search the indexed FAA documents (CFR sections, Advisory Circulars, etc.) for relevant information.

Use this tool FIRST when answering questions about FAA regulations. It searches the pre-indexed knowledge base for relevant content.

When to use:
- User asks a general question about FAA certification
- Looking for relevant regulations on a topic
- Finding Advisory Circulars related to a requirement
- Before fetching specific CFR sections (to find which ones are relevant)

The search returns document snippets with citations. If you need the complete text of a specific section found in results, use fetch_cfr_section.
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
                "description": "Number of results to return (default: 5, max: 10)",
                "default": 5,
            },
            "doc_type": {
                "type": "string",
                "description": "Optional: filter by document type",
                "enum": ["cfr", "ac", "order", "policy"],
            },
        },
        "required": ["query"],
    },
}
