"""
Document management tools for personal document index (BYOD).

These tools allow users to list and delete their uploaded documents
through the chat interface.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Tool definitions for Claude API

LIST_MY_DOCUMENTS_DEFINITION: dict[str, Any] = {
    "name": "list_my_documents",
    "description": """List all documents that the user has uploaded to their personal document index.
Returns document metadata including titles, upload dates, and document IDs.
Use this when the user asks about their uploaded documents or wants to see what they've added.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {
                "type": "string",
                "description": "The index to search (faa-agent, nrc-agent, dod-agent). Defaults to faa-agent.",
                "enum": ["faa-agent", "nrc-agent", "dod-agent"],
            }
        },
        "required": [],
    },
}

DELETE_MY_DOCUMENT_DEFINITION: dict[str, Any] = {
    "name": "delete_my_document",
    "description": """Delete a document from the user's personal document index.
Requires the document_id which can be obtained from list_my_documents.
Use this when the user explicitly asks to remove or delete one of their uploaded documents.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "The ID of the document to delete. Get this from list_my_documents.",
            },
            "index": {
                "type": "string",
                "description": "The index containing the document (faa-agent, nrc-agent, dod-agent). Defaults to faa-agent.",
                "enum": ["faa-agent", "nrc-agent", "dod-agent"],
            }
        },
        "required": ["document_id"],
    },
}

FETCH_PERSONAL_DOCUMENT_DEFINITION: dict[str, Any] = {
    "name": "fetch_personal_document",
    "description": """Fetch the complete text of an uploaded personal document.

Use this tool when:
- Search results include a personal document and you need full context to answer accurately
- User asks detailed questions about their uploaded document
- You need to verify exact wording or find specific information in the document

This retrieves and reassembles the full document text from all chunks. For large documents 
(>50,000 chars), the response will be truncated with an offer to search the remainder.

The document content is authoritative - base your answers on what it actually says.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "The ID of the document to fetch. Get this from list_my_documents or search results.",
            },
            "index": {
                "type": "string",
                "description": "The index containing the document (faa-agent, nrc-agent, dod-agent). Defaults to faa-agent.",
                "enum": ["faa-agent", "nrc-agent", "dod-agent"],
            }
        },
        "required": ["document_id"],
    },
}

SEARCH_PERSONAL_DOCUMENT_DEFINITION: dict[str, Any] = {
    "name": "search_personal_document",
    "description": """Semantically search within a personal document for specific topics.

Use this tool when:
- fetch_personal_document returned truncated content and you need to find information in the remainder
- User asks about a specific topic that wasn't in the visible portion of a large document
- You need to find all mentions of a concept throughout a document

This performs semantic search (not just keyword matching) on the full document text,
returning the most relevant passages with surrounding context.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "The ID of the document to search. Must have been previously fetched or will be fetched automatically.",
            },
            "query": {
                "type": "string",
                "description": "The topic, question, or concept to search for in the document.",
            },
            "index": {
                "type": "string",
                "description": "The index containing the document (faa-agent, nrc-agent, dod-agent). Defaults to faa-agent.",
                "enum": ["faa-agent", "nrc-agent", "dod-agent"],
            }
        },
        "required": ["document_id", "query"],
    },
}


async def list_my_documents(
    fingerprint: Optional[str] = None,
    index: str = "faa-agent",
) -> str:
    """
    List all documents uploaded by this user.
    
    Args:
        fingerprint: User fingerprint for isolation (injected by orchestrator)
        index: The index to query
        
    Returns:
        Formatted string listing user's documents
    """
    if not fingerprint:
        return "Error: Unable to identify user. Please ensure you're properly authenticated."
    
    settings = get_settings()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{settings.search_proxy_url}/documents",
                params={
                    "fingerprint": fingerprint,
                    "index": index,
                }
            )
            
            if response.status_code != 200:
                error_detail = response.json().get("detail", "Unknown error")
                logger.error(f"Failed to list documents: {error_detail}")
                return f"Error listing documents: {error_detail}"
            
            data = response.json()
            documents = data.get("documents", [])
            
            if not documents:
                return "You haven't uploaded any documents yet. You can upload PDFs using the document upload feature."
            
            # Format the response
            lines = [f"You have {len(documents)} uploaded document(s):\n"]
            
            for i, doc in enumerate(documents, 1):
                title = doc.get("title", "Untitled")
                doc_id = doc.get("id", "unknown")
                uploaded_at = doc.get("uploaded_at", "unknown date")
                page_count = doc.get("page_count", "?")
                chunk_count = doc.get("chunk_count", 1)
                
                # Format date if it's a timestamp
                if uploaded_at and "T" in str(uploaded_at):
                    # Parse ISO format and make it readable
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
                        uploaded_at = dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pass
                
                lines.append(f"{i}. **{title}**")
                lines.append(f"   - Document ID: `{doc_id}`")
                lines.append(f"   - Uploaded: {uploaded_at}")
                lines.append(f"   - Pages: {page_count}, Chunks: {chunk_count}")
                lines.append("")
            
            return "\n".join(lines)
            
    except httpx.RequestError as e:
        logger.error(f"Request error listing documents: {e}")
        return f"Error connecting to document service: {e}"
    except Exception as e:
        logger.error(f"Unexpected error listing documents: {e}")
        return f"Error listing documents: {e}"


async def delete_my_document(
    document_id: str,
    fingerprint: Optional[str] = None,
    index: str = "faa-agent",
) -> str:
    """
    Delete a document from the user's personal index.
    
    Args:
        document_id: ID of the document to delete
        fingerprint: User fingerprint for isolation (injected by orchestrator)
        index: The index containing the document
        
    Returns:
        Confirmation message or error
    """
    if not fingerprint:
        return "Error: Unable to identify user. Please ensure you're properly authenticated."
    
    if not document_id:
        return "Error: No document ID provided. Use list_my_documents to see your documents and their IDs."
    
    settings = get_settings()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{settings.search_proxy_url}/documents/{document_id}",
                params={
                    "fingerprint": fingerprint,
                    "index": index,
                }
            )
            
            if response.status_code == 404:
                return f"Document with ID `{document_id}` was not found. It may have already been deleted, or you may not have permission to delete it."
            
            if response.status_code == 403:
                return "You don't have permission to delete this document. You can only delete documents you uploaded."
            
            if response.status_code != 200:
                error_detail = response.json().get("detail", "Unknown error")
                logger.error(f"Failed to delete document: {error_detail}")
                return f"Error deleting document: {error_detail}"
            
            data = response.json()
            deleted_count = data.get("chunks_deleted", 0)
            
            if deleted_count > 0:
                return f"Successfully deleted document `{document_id}` and all its chunks ({deleted_count} chunk(s) removed)."
            else:
                return f"Document `{document_id}` was not found or has already been deleted."
            
    except httpx.RequestError as e:
        logger.error(f"Request error deleting document: {e}")
        return f"Error connecting to document service: {e}"
    except Exception as e:
        logger.error(f"Unexpected error deleting document: {e}")
        return f"Error deleting document: {e}"


# Constants for document grounding
# Token budget: aim for ~20K tokens per tool result to stay well under 200K context limit
# With ~4 chars per token, that's ~80K chars max, but be conservative
MAX_INITIAL_CHARS = 25000  # ~12 pages for initial fetch (~6K tokens)
MAX_FULL_CHARS = 50000     # ~25 pages max for cache
MAX_SEARCH_RESULT_CHARS = 8000  # Max chars in search results (~2K tokens)


async def fetch_personal_document(
    document_id: str,
    fingerprint: Optional[str] = None,
    index: str = "faa-agent",
    personal_doc_cache: Optional[dict] = None,
) -> str:
    """
    Fetch the complete text of an uploaded personal document.
    
    Args:
        document_id: ID of the document to fetch
        fingerprint: User fingerprint for isolation (injected by orchestrator)
        index: The index containing the document
        personal_doc_cache: Conversation-scoped cache for full document text
        
    Returns:
        Document text (possibly truncated) with metadata header
    """
    if not fingerprint:
        return "Error: Unable to identify user. Please ensure you're properly authenticated."
    
    if not document_id:
        return "Error: No document ID provided. Use list_my_documents to see your documents and their IDs."
    
    settings = get_settings()
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{settings.search_proxy_url}/documents/{document_id}/content",
                params={
                    "fingerprint": fingerprint,
                    "index": index,
                }
            )
            
            if response.status_code == 404:
                return f"Document with ID `{document_id}` was not found. Use list_my_documents to see your uploaded documents."
            
            if response.status_code == 403:
                return "You don't have permission to access this document. You can only access documents you uploaded."
            
            if response.status_code != 200:
                error_detail = response.json().get("detail", "Unknown error")
                logger.error(f"Failed to fetch document: {error_detail}")
                return f"Error fetching document: {error_detail}"
            
            data = response.json()
            
            title = data.get("title", "Untitled")
            content = data.get("content", "")
            total_chars = data.get("total_chars", len(content))
            chunk_count = data.get("chunk_count", 1)
            page_count = data.get("page_count", "unknown")
            
            # Cache full content for follow-up searches
            if personal_doc_cache is not None:
                cache_content = content[:MAX_FULL_CHARS]  # Limit cache size
                personal_doc_cache[f"personal_doc_{document_id}"] = cache_content
                logger.info(f"Cached document {document_id[:16]}... ({len(cache_content)} chars)")
            
            # Format response with metadata header
            lines = [
                f"## {title}",
                f"**Document ID:** `{document_id}`",
                f"**Pages:** {page_count} | **Chunks:** {chunk_count} | **Total characters:** {total_chars:,}",
                "",
                "---",
                "",
            ]
            
            # Truncate if needed
            if len(content) > MAX_INITIAL_CHARS:
                truncated_content = content[:MAX_INITIAL_CHARS]
                lines.append(truncated_content)
                lines.append("")
                lines.append("---")
                lines.append("")
                lines.append(f"**[Document truncated at {MAX_INITIAL_CHARS:,} characters. Full document is {total_chars:,} characters.]**")
                lines.append("")
                lines.append("I can search the full document for specific topics. What would you like me to find?")
            else:
                lines.append(content)
            
            return "\n".join(lines)
            
    except httpx.RequestError as e:
        logger.error(f"Request error fetching document: {e}")
        return f"Error connecting to document service: {e}"
    except Exception as e:
        logger.error(f"Unexpected error fetching document: {e}")
        return f"Error fetching document: {e}"


async def search_personal_document(
    document_id: str,
    query: str,
    fingerprint: Optional[str] = None,
    index: str = "faa-agent",
    personal_doc_cache: Optional[dict] = None,
) -> str:
    """
    Semantically search within a personal document for specific topics.
    
    Uses Azure AI Search hybrid search (vector + keyword) on the document's
    indexed chunks for fast, accurate results.
    
    Args:
        document_id: ID of the document to search
        query: Topic or question to search for
        fingerprint: User fingerprint for isolation (injected by orchestrator)
        index: The index containing the document
        personal_doc_cache: Unused (kept for API compatibility)
        
    Returns:
        Relevant passages from the document
    """
    if not fingerprint:
        return "Error: Unable to identify user. Please ensure you're properly authenticated."
    
    if not document_id:
        return "Error: No document ID provided."
    
    if not query:
        return "Error: No search query provided. Please specify what you want to find in the document."
    
    settings = get_settings()
    
    # Use the search proxy's search endpoint with document filter
    # This leverages Azure AI Search's hybrid search (vector + keyword) on indexed chunks
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.search_proxy_url}/search",
                json={
                    "query": query,
                    "fingerprint": fingerprint,
                    "index": index,
                    "top": 10,
                    "doc_type": "user_upload",  # Only search user uploads
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Search proxy error: {response.status_code} - {response.text}")
                return f"Error searching document: HTTP {response.status_code}"
            
            data = response.json()
            results = data.get("results", [])
            
            # Filter to only results from this specific document
            doc_results = [
                r for r in results 
                if r.get("id", "").startswith(document_id)
            ]
            
            if not doc_results:
                return f"No relevant passages found for '{query}' in this document."
            
            # Format results
            output_lines = [f"## Search Results for: {query}\n\n**Document:** {document_id}\n\n---\n"]
            
            for r in doc_results:
                score = r.get("score", 0)
                content = r.get("content", "")
                # Clean up content
                content = content.strip()
                if content:
                    output_lines.append(f"\n**[Relevance: {score:.2f}]**\n\n{content}\n\n---")
            
            return "\n".join(output_lines)
            
    except httpx.RequestError as e:
        logger.error(f"Request error searching document: {e}")
        return f"Error connecting to search service: {e}"
    except Exception as e:
        logger.error(f"Unexpected error searching document: {e}")
        return f"Error searching document: {e}"


# NOTE: The _generate_embedding, _cosine_similarity, and _keyword_search helper 
# functions were removed. search_personal_document now uses the search proxy's 
# /search endpoint which leverages Azure AI Search's native hybrid search on 
# already-indexed document chunks. This is much faster than computing embeddings
# for every paragraph on-the-fly.
