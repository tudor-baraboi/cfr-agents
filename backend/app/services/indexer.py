"""
Document indexer for Azure AI Search.

Handles background indexing of documents to the vector search index.
Used for progressive indexing of cached documents.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, List, Optional

import httpx

from app.config import get_settings
from app.services.cache import get_cache

logger = logging.getLogger(__name__)

# Cohere embed-v3-english produces 1024-dimensional vectors
EMBEDDING_DIMENSIONS = 1024


async def generate_embedding(
    text: str,
    input_type: str = "document",
) -> Optional[List[float]]:
    """
    Generate embedding using Azure AI Services Cohere model.
    
    Args:
        text: Text to embed (truncated to 8000 chars)
        input_type: 'document' for indexing, 'query' for search queries
    
    Returns:
        1024-dimensional embedding vector or None on error.
    """
    results = await generate_embeddings_batch([text], input_type=input_type)
    return results[0] if results else None


async def generate_embeddings_batch(
    texts: List[str],
    input_type: str = "document",
    batch_size: int = 20,
) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts in batches.
    
    Much faster than sequential calls - batches up to 20 texts per API call.
    
    Args:
        texts: List of texts to embed
        input_type: 'document' for indexing, 'query' for search queries
        batch_size: Max texts per API call (Cohere limit is ~96, using 20 for safety)
    
    Returns:
        List of embedding vectors (or None for failed texts)
    """
    settings = get_settings()
    
    if not settings.azure_ai_services_endpoint or not settings.azure_ai_services_key:
        logger.warning("Azure AI Services not configured, skipping embeddings")
        return [None] * len(texts)
    
    endpoint = settings.azure_ai_services_endpoint.rstrip('/')
    url = f"{endpoint}/models/embeddings?api-version=2024-05-01-preview"
    
    results: List[Optional[List[float]]] = []
    
    # Process in batches
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            truncated_batch = [t[:8000] for t in batch]  # Truncate each text
            
            try:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {settings.azure_ai_services_key}",
                        "Content-Type": "application/json",
                        "extra-parameters": "pass-through",
                    },
                    json={
                        "input": truncated_batch,
                        "model": settings.azure_ai_services_embedding_deployment,
                        "input_type": input_type,
                    },
                )
                response.raise_for_status()
                data = response.json()
                
                # Extract embeddings in order
                for item in data["data"]:
                    results.append(item["embedding"])
                    
            except Exception as e:
                logger.error(f"Batch embedding error for batch {i//batch_size + 1}: {e}")
                # Return None for this batch
                results.extend([None] * len(batch))
    
    return results


async def upload_to_index(doc: dict[str, Any], index_name: str | None = None) -> bool:
    """
    Upload a document to Azure AI Search index.
    
    Args:
        doc: Document with id, title, content, content_vector, etc.
        index_name: Optional index name override. Defaults to settings.azure_search_index.
    
    Returns:
        True if successful.
    """
    settings = get_settings()
    endpoint = settings.azure_search_endpoint
    index = index_name or settings.azure_search_index
    api_key = settings.azure_search_key
    
    if not endpoint or not api_key:
        logger.error("Azure Search not configured")
        return False
    
    url = f"{endpoint}/indexes/{index}/docs/index?api-version=2024-07-01"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": api_key,
                },
                json={
                    "value": [
                        {
                            "@search.action": "upload",
                            **doc,
                        }
                    ]
                },
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Index upload error for {doc.get('id')}: {e}")
            return False


async def index_document(
    content: str,
    doc_type: str,
    doc_id: str,
    title: str,
    source_url: str = "",
    cache_key: str | None = None,
    index_name: str | None = None,
) -> bool:
    """
    Index a document in Azure AI Search.
    
    This function:
    1. Generates embedding for the content
    2. Uploads to the search index
    3. Marks the cached document as indexed (if cache_key provided)
    
    Args:
        content: Document text content
        doc_type: "cfr" or "drs"
        doc_id: Document identifier (e.g., "14-25-1309" or "AC-25.1309-1A")
        title: Document title
        source_url: Original source URL
        cache_key: Cache key to mark as indexed after success
    
    Returns:
        True if indexing succeeded.
    """
    settings = get_settings()
    
    # Check if indexing is enabled
    if not settings.auto_index_on_cache_hit:
        logger.debug("Auto-indexing disabled, skipping")
        return False
    
    logger.info(f"Indexing document: {doc_type}/{doc_id}")
    
    # Generate unique ID
    unique_id = hashlib.sha256(f"{doc_type}:{doc_id}".encode()).hexdigest()[:16]
    
    # Generate embedding
    embedding = await generate_embedding(content, input_type="document")
    
    if not embedding:
        logger.warning(f"Could not generate embedding for {doc_id}")
        # Still index without vector for keyword search
        embedding = None
    
    # Prepare document for index (must match index schema)
    # Schema fields: id, title, content, source, doc_type, citation, embedding
    doc = {
        "id": unique_id,
        "title": title,
        "content": content[:32000],  # Truncate for index limit
        "doc_type": doc_type,
        "source": source_url,
        "citation": doc_id,
    }
    
    if embedding:
        doc["embedding"] = embedding
    
    # Upload to index
    success = await upload_to_index(doc, index_name=index_name)
    
    if success and cache_key:
        # Mark as indexed in cache
        cache = get_cache()
        await cache.mark_indexed(cache_key)
    
    if success:
        logger.info(f"Successfully indexed: {doc_type}/{doc_id}")
    
    return success


def schedule_indexing(
    content: str,
    doc_type: str,
    doc_id: str,
    title: str,
    source_url: str = "",
    cache_key: str | None = None,
    index_name: str | None = None,
) -> asyncio.Task:
    """
    Schedule background indexing of a document.
    
    This creates an async task that runs in the background.
    The task will index the document without blocking the caller.
    
    Args:
        index_name: Optional index name override (e.g., 'nrc-agent' for NRC documents).
    
    Returns:
        The asyncio Task object (can be awaited if needed).
    """
    logger.info(f"Scheduling background indexing for: {doc_type}/{doc_id} -> index: {index_name or 'default'}")
    
    async def _index_task():
        try:
            await index_document(
                content=content,
                doc_type=doc_type,
                doc_id=doc_id,
                title=title,
                source_url=source_url,
                cache_key=cache_key,
                index_name=index_name,
            )
        except Exception as e:
            logger.error(f"Background indexing failed for {doc_id}: {e}")
    
    return asyncio.create_task(_index_task())
