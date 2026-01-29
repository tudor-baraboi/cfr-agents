"""
Search Proxy Service.

This service is the ONLY component with Azure AI Search credentials.
It enforces fingerprint-based filtering on EVERY search request.

Endpoints:
- POST /search - Query index with enforced fingerprint filter
- POST /index - Add document chunks (validates fingerprint match)
- GET /documents - List user's uploaded documents
- DELETE /documents/{id} - Delete a user's document

Security Model:
- Backend has NO Azure Search credentials
- Cannot bypass fingerprint filter
- Cannot query/modify other users' documents
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, List

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from search_proxy.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Search Proxy",
    description="Fingerprint-enforced search proxy for personal document isolation",
    version="1.0.0",
)


# -----------------------------------------------------------------------------
# Request/Response Models
# -----------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Search request with mandatory fingerprint."""

    query: str = Field(..., description="Search query text")
    index: str = Field(..., description="Index name (faa-agent, nrc-agent, dod-agent)")
    fingerprint: str = Field(..., min_length=10, description="User's browser fingerprint")
    top: int = Field(default=5, ge=1, le=20, description="Number of results to return")
    doc_type: Optional[str] = Field(default=None, description="Optional filter by document type")


class SearchResult(BaseModel):
    """Single search result."""

    id: str
    title: str
    content: str
    source: str
    doc_type: Optional[str] = None
    citation: Optional[str] = None
    owner_fingerprint: Optional[str] = None
    score: Optional[float] = None


class SearchResponse(BaseModel):
    """Search response with results."""

    results: List[SearchResult]
    total_count: int


class IndexDocument(BaseModel):
    """Document to index."""

    id: str
    title: str
    content: str
    source: str
    doc_type: str
    citation: Optional[str] = None
    owner_fingerprint: str
    uploaded_at: str
    page_count: Optional[int] = None
    file_hash: Optional[str] = None
    embedding: Optional[List[float]] = None


class IndexRequest(BaseModel):
    """Index request with documents."""

    index: str = Field(..., description="Index name")
    fingerprint: str = Field(..., min_length=10, description="User's browser fingerprint")
    documents: List[IndexDocument]


class IndexResponse(BaseModel):
    """Index response."""

    indexed_count: int
    failed_count: int
    errors: List[str] = []


class DocumentInfo(BaseModel):
    """Document metadata for listing."""

    id: str
    title: str
    filename: Optional[str] = None
    uploaded_at: str
    page_count: Optional[int] = None
    chunk_count: int = 0
    file_hash: Optional[str] = None


class DocumentsResponse(BaseModel):
    """Response for document listing."""

    documents: List[DocumentInfo]
    total_count: int


class DocumentContent(BaseModel):
    """Full document content reassembled from chunks."""

    id: str
    title: str
    content: str
    page_count: Optional[int] = None
    chunk_count: int
    uploaded_at: str
    total_chars: int
    truncated: bool = False


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


async def generate_query_embedding(query: str) -> Optional[List[float]]:
    """Generate embedding for search query using Azure AI Services Cohere model."""
    settings = get_settings()

    if not settings.azure_ai_services_endpoint or not settings.azure_ai_services_key:
        logger.warning("Azure AI Services not configured, falling back to keyword search")
        return None

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
                    "input_type": "query",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.warning(f"Failed to generate query embedding: {e}")
            return None


def validate_index(index: str) -> None:
    """Validate index name is allowed."""
    settings = get_settings()
    if index not in settings.valid_indexes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid index '{index}'. Must be one of: {settings.valid_indexes}",
        )


def build_fingerprint_filter(fingerprint: str, doc_type: Optional[str] = None) -> str:
    """
    Build OData filter that enforces fingerprint isolation.
    
    Returns documents where:
    - owner_fingerprint is null (regulatory docs visible to all)
    - OR owner_fingerprint matches the user's fingerprint
    """
    # Base filter: null (regulatory) OR user's own documents
    fp_filter = f"(owner_fingerprint eq null or owner_fingerprint eq '{fingerprint}')"

    if doc_type:
        return f"({fp_filter}) and (doc_type eq '{doc_type}')"

    return fp_filter


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "search-proxy"}


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    """
    Search index with enforced fingerprint filtering.
    
    The fingerprint filter is ALWAYS applied - this cannot be bypassed.
    Returns regulatory documents (owner_fingerprint=null) + user's own documents.
    """
    settings = get_settings()
    validate_index(request.index)

    if not settings.azure_search_endpoint or not settings.azure_search_key:
        raise HTTPException(status_code=503, detail="Azure Search not configured")

    url = f"{settings.azure_search_endpoint}/indexes/{request.index}/docs/search?api-version=2024-07-01"

    # Build search body with ENFORCED fingerprint filter
    search_body: dict[str, Any] = {
        "search": request.query,
        "top": request.top,
        "select": "id,title,content,source,doc_type,citation,owner_fingerprint",
        "queryType": "simple",
        "filter": build_fingerprint_filter(request.fingerprint, request.doc_type),
    }

    # Generate embedding for hybrid search
    query_embedding = await generate_query_embedding(request.query)
    if query_embedding:
        search_body["vectorQueries"] = [
            {
                "kind": "vector",
                "vector": query_embedding,
                "fields": "embedding",
                "k": request.top,
            }
        ]
        logger.info(f"Hybrid search: '{request.query}' for fingerprint {request.fingerprint[:8]}...")
    else:
        logger.info(f"Keyword search: '{request.query}' for fingerprint {request.fingerprint[:8]}...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": settings.azure_search_key,
                },
                json=search_body,
            )
            response.raise_for_status()
            data = response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Azure Search HTTP error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=502, detail=f"Search error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Azure Search error: {e}")
            raise HTTPException(status_code=502, detail=f"Search error: {e}")

    # Convert results
    results = []
    for doc in data.get("value", []):
        results.append(
            SearchResult(
                id=doc.get("id", ""),
                title=doc.get("title", ""),
                content=doc.get("content", "")[:1000],  # Truncate for response
                source=doc.get("source", ""),
                doc_type=doc.get("doc_type"),
                citation=doc.get("citation"),
                owner_fingerprint=doc.get("owner_fingerprint"),
                score=doc.get("@search.score"),
            )
        )

    return SearchResponse(results=results, total_count=len(results))


@app.post("/index", response_model=IndexResponse)
async def index_documents(request: IndexRequest) -> IndexResponse:
    """
    Add document chunks to the index.
    
    Validation:
    - owner_fingerprint in ALL documents must match request fingerprint
    - Cannot upload with owner_fingerprint=null (protects regulatory docs)
    """
    settings = get_settings()
    validate_index(request.index)

    if not settings.azure_search_endpoint or not settings.azure_search_key:
        raise HTTPException(status_code=503, detail="Azure Search not configured")

    # Validate ALL documents have matching fingerprint
    for doc in request.documents:
        if doc.owner_fingerprint != request.fingerprint:
            raise HTTPException(
                status_code=403,
                detail=f"Document fingerprint mismatch. Cannot upload documents for other users.",
            )
        if not doc.owner_fingerprint:
            raise HTTPException(
                status_code=403,
                detail="Cannot upload documents with null owner_fingerprint (regulatory docs protected)",
            )

    url = f"{settings.azure_search_endpoint}/indexes/{request.index}/docs/index?api-version=2024-07-01"

    # Convert documents to Azure Search format
    docs_to_upload = []
    for doc in request.documents:
        upload_doc: dict[str, Any] = {
            "@search.action": "upload",
            "id": doc.id,
            "title": doc.title,
            "content": doc.content,
            "source": doc.source,
            "doc_type": doc.doc_type,
            "owner_fingerprint": doc.owner_fingerprint,
            "uploaded_at": doc.uploaded_at,
        }
        if doc.citation:
            upload_doc["citation"] = doc.citation
        if doc.page_count is not None:
            upload_doc["page_count"] = doc.page_count
        if doc.file_hash:
            upload_doc["file_hash"] = doc.file_hash
        if doc.embedding:
            upload_doc["embedding"] = doc.embedding

        docs_to_upload.append(upload_doc)

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": settings.azure_search_key,
                },
                json={"value": docs_to_upload},
            )
            response.raise_for_status()
            data = response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Azure Search index error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=502, detail=f"Index error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Azure Search index error: {e}")
            raise HTTPException(status_code=502, detail=f"Index error: {e}")

    # Count successes and failures
    results = data.get("value", [])
    indexed = sum(1 for r in results if r.get("status") is True or r.get("statusCode") == 200 or r.get("statusCode") == 201)
    failed = len(results) - indexed
    errors = [r.get("errorMessage", "") for r in results if r.get("status") is False]

    logger.info(f"Indexed {indexed}/{len(request.documents)} documents for fingerprint {request.fingerprint[:8]}...")

    return IndexResponse(indexed_count=indexed, failed_count=failed, errors=[e for e in errors if e])


@app.get("/documents", response_model=DocumentsResponse)
async def list_documents(fingerprint: str, index: str) -> DocumentsResponse:
    """
    List documents uploaded by a specific user.
    
    Only returns documents where owner_fingerprint matches the request fingerprint.
    Groups by base document ID (without chunk suffix) to show unique documents.
    """
    settings = get_settings()
    validate_index(index)

    if len(fingerprint) < 10:
        raise HTTPException(status_code=400, detail="Invalid fingerprint (too short)")

    if not settings.azure_search_endpoint or not settings.azure_search_key:
        raise HTTPException(status_code=503, detail="Azure Search not configured")

    url = f"{settings.azure_search_endpoint}/indexes/{index}/docs/search?api-version=2024-07-01"

    # Search for user's documents only (NOT regulatory docs)
    search_body = {
        "search": "*",
        "top": 1000,  # Get all user's documents
        "select": "id,title,uploaded_at,page_count,file_hash,owner_fingerprint",
        "filter": f"owner_fingerprint eq '{fingerprint}'",
        "orderby": "uploaded_at desc",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": settings.azure_search_key,
                },
                json=search_body,
            )
            response.raise_for_status()
            data = response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Azure Search error: {e.response.status_code}")
            raise HTTPException(status_code=502, detail=f"Search error: {e.response.status_code}")

    # Group chunks by base document ID (remove -chunkN suffix)
    doc_map: dict[str, dict[str, Any]] = {}

    for doc in data.get("value", []):
        doc_id = doc.get("id", "")
        # Extract base ID (format: fingerprint-docname-chunkN)
        parts = doc_id.rsplit("-chunk", 1)
        base_id = parts[0]

        if base_id not in doc_map:
            doc_map[base_id] = {
                "id": base_id,
                "title": doc.get("title", ""),
                "filename": doc.get("title", ""),  # Title is usually filename
                "uploaded_at": doc.get("uploaded_at", ""),
                "page_count": doc.get("page_count"),
                "file_hash": doc.get("file_hash"),
                "chunk_count": 0,
            }
        doc_map[base_id]["chunk_count"] += 1

    documents = [
        DocumentInfo(
            id=d["id"],
            title=d["title"],
            filename=d["filename"],
            uploaded_at=d["uploaded_at"],
            page_count=d["page_count"],
            chunk_count=d["chunk_count"],
            file_hash=d["file_hash"],
        )
        for d in doc_map.values()
    ]

    return DocumentsResponse(documents=documents, total_count=len(documents))


@app.get("/documents/{document_id}/content", response_model=DocumentContent)
async def get_document_content(document_id: str, fingerprint: str, index: str) -> DocumentContent:
    """
    Fetch the full content of a personal document by reassembling all chunks.
    
    This endpoint enforces ownership - only the document owner can fetch content.
    Chunks are ordered by their suffix (-chunk0, -chunk1, etc.) and concatenated.
    """
    settings = get_settings()
    validate_index(index)

    if len(fingerprint) < 10:
        raise HTTPException(status_code=400, detail="Invalid fingerprint (too short)")

    if not settings.azure_search_endpoint or not settings.azure_search_key:
        raise HTTPException(status_code=503, detail="Azure Search not configured")

    url = f"{settings.azure_search_endpoint}/indexes/{index}/docs/search?api-version=2024-07-01"

    # Search for all chunks of this document owned by this user
    search_body = {
        "search": "*",
        "top": 1000,  # Support large documents (up to 1000 chunks)
        "select": "id,title,content,uploaded_at,page_count,owner_fingerprint",
        "filter": f"owner_fingerprint eq '{fingerprint}'",
        "orderby": "id asc",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": settings.azure_search_key,
                },
                json=search_body,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Azure Search error: {e.response.status_code}")
            raise HTTPException(status_code=502, detail=f"Search error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Azure Search error: {e}")
            raise HTTPException(status_code=502, detail=f"Search error: {e}")

    # Filter to chunks belonging to this document
    chunks = []
    doc_title = ""
    doc_uploaded_at = ""
    doc_page_count = None

    for doc in data.get("value", []):
        doc_id = doc.get("id", "")
        # Match base ID or chunk IDs (format: base-id-chunkN)
        if doc_id == document_id or doc_id.startswith(f"{document_id}-chunk"):
            # Verify ownership
            if doc.get("owner_fingerprint") != fingerprint:
                raise HTTPException(
                    status_code=403,
                    detail="Cannot access document owned by another user",
                )
            chunks.append(doc)
            # Capture metadata from first chunk
            if not doc_title:
                doc_title = doc.get("title", "")
            if not doc_uploaded_at:
                doc_uploaded_at = doc.get("uploaded_at", "")
            if doc_page_count is None:
                doc_page_count = doc.get("page_count")

    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found")

    # Sort chunks by their chunk number
    def get_chunk_num(doc: dict) -> int:
        doc_id = doc.get("id", "")
        if "-chunk" in doc_id:
            try:
                return int(doc_id.rsplit("-chunk", 1)[1])
            except (ValueError, IndexError):
                return 0
        return 0

    chunks.sort(key=get_chunk_num)

    # Reassemble full content
    full_content = "\n\n".join(doc.get("content", "") for doc in chunks)
    total_chars = len(full_content)

    logger.info(f"Fetched {len(chunks)} chunks for document {document_id[:20]}... ({total_chars} chars)")

    return DocumentContent(
        id=document_id,
        title=doc_title,
        content=full_content,
        page_count=doc_page_count,
        chunk_count=len(chunks),
        uploaded_at=doc_uploaded_at,
        total_chars=total_chars,
        truncated=False,  # Proxy returns full content; tool handles truncation
    )


@app.delete("/documents/{document_id}")
async def delete_document(document_id: str, fingerprint: str, index: str) -> dict[str, Any]:
    """
    Delete a user's document and all its chunks.
    
    Validation:
    - Only deletes if owner_fingerprint matches request fingerprint
    - Returns 403 if trying to delete someone else's document
    """
    settings = get_settings()
    validate_index(index)

    if len(fingerprint) < 10:
        raise HTTPException(status_code=400, detail="Invalid fingerprint (too short)")

    if not settings.azure_search_endpoint or not settings.azure_search_key:
        raise HTTPException(status_code=503, detail="Azure Search not configured")

    # First, find all chunks belonging to this document
    search_url = f"{settings.azure_search_endpoint}/indexes/{index}/docs/search?api-version=2024-07-01"

    # Search for document and all its chunks
    search_body = {
        "search": "*",
        "top": 1000,
        "select": "id,owner_fingerprint",
        "filter": f"owner_fingerprint eq '{fingerprint}'",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                search_url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": settings.azure_search_key,
                },
                json=search_body,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"Search error during delete: {e}")
            raise HTTPException(status_code=502, detail="Failed to find document")

    # Find matching document IDs (base ID or chunks starting with base ID)
    chunks_to_delete = []
    for doc in data.get("value", []):
        doc_id = doc.get("id", "")
        if doc_id == document_id or doc_id.startswith(f"{document_id}-chunk"):
            # Verify ownership
            if doc.get("owner_fingerprint") != fingerprint:
                raise HTTPException(
                    status_code=403,
                    detail="Cannot delete document owned by another user",
                )
            chunks_to_delete.append({"@search.action": "delete", "id": doc_id})

    if not chunks_to_delete:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete the chunks
    index_url = f"{settings.azure_search_endpoint}/indexes/{index}/docs/index?api-version=2024-07-01"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                index_url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": settings.azure_search_key,
                },
                json={"value": chunks_to_delete},
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Delete error: {e}")
            raise HTTPException(status_code=502, detail="Failed to delete document")

    logger.info(f"Deleted {len(chunks_to_delete)} chunks for document {document_id[:20]}...")

    return {
        "status": "deleted",
        "document_id": document_id,
        "chunks_deleted": len(chunks_to_delete),
    }


# Run with: uvicorn main:app --port 8001
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
