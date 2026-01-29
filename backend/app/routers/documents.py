"""
Document upload endpoints.

Handles PDF upload, text extraction (with OCR fallback), chunking,
embedding generation, and indexing via the search proxy.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional, List

import fitz  # PyMuPDF
import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.services.indexer import generate_embedding

# OCR imports (optional - graceful fallback if not available)
try:
    import pytesseract
    from pdf2image import convert_from_bytes
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Limits
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_DOCUMENTS_PER_USER = 20
MAX_CHUNKS_PER_DOCUMENT = 100
CHUNK_SIZE_CHARS = 4000  # ~1000 tokens
MIN_CHARS_PER_PAGE = 100  # Below this, use OCR


class DocumentUploadResponse(BaseModel):
    """Response for document upload."""
    id: str
    title: str
    page_count: int
    chunk_count: int
    status: str


class DocumentInfo(BaseModel):
    """Document metadata."""
    id: str
    title: str
    filename: Optional[str] = None
    uploaded_at: str
    page_count: Optional[int] = None
    chunk_count: int = 0
    file_hash: Optional[str] = None


class DocumentsListResponse(BaseModel):
    """Response for listing documents."""
    documents: List[DocumentInfo]
    total_count: int


def compute_file_hash(content: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()


def extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, int]:
    """
    Extract text from PDF using PyMuPDF, with OCR fallback for scanned PDFs.
    
    Strategy:
    1. Try PyMuPDF text extraction (fast, works for digital PDFs)
    2. If text is too sparse (likely a scanned PDF), use OCR via pytesseract
    
    Returns:
        (full_text, page_count)
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    
    # First pass: try regular text extraction
    all_text = []
    total_chars = 0
    
    for page in doc:
        text = page.get_text("text")
        all_text.append(text)
        total_chars += len(text.strip())
    
    doc.close()
    
    # Check if we got enough text
    avg_chars_per_page = total_chars / max(page_count, 1)
    
    if avg_chars_per_page >= MIN_CHARS_PER_PAGE:
        # Good text extraction - this is a digital PDF
        logger.info(f"Digital PDF: extracted {total_chars} chars from {page_count} pages ({avg_chars_per_page:.0f} chars/page)")
        return "\n\n".join(all_text), page_count
    
    # Low text content - likely a scanned PDF, try OCR
    logger.info(f"Low text content ({avg_chars_per_page:.0f} chars/page), attempting OCR...")
    
    if not OCR_AVAILABLE:
        logger.warning("OCR not available (pytesseract/pdf2image not installed). Returning sparse text.")
        return "\n\n".join(all_text), page_count
    
    try:
        return _extract_text_with_ocr(pdf_bytes, page_count)
    except Exception as e:
        logger.error(f"OCR failed: {e}. Falling back to sparse text.")
        return "\n\n".join(all_text), page_count


def _extract_text_with_ocr(pdf_bytes: bytes, page_count: int) -> tuple[str, int]:
    """
    Extract text from scanned PDF using OCR (pytesseract + pdf2image).
    
    Args:
        pdf_bytes: Raw PDF file bytes
        page_count: Number of pages (for logging)
        
    Returns:
        (full_text, page_count)
    """
    # Convert PDF pages to images
    # Using 200 DPI for good balance between quality and speed
    logger.info(f"Converting {page_count} PDF pages to images for OCR...")
    images = convert_from_bytes(pdf_bytes, dpi=200, fmt='png')
    
    all_text = []
    total_chars = 0
    
    for i, image in enumerate(images):
        # Run OCR on each page image
        page_text = pytesseract.image_to_string(image, lang='eng')
        all_text.append(page_text)
        total_chars += len(page_text.strip())
        
        # Log progress for large documents
        if (i + 1) % 10 == 0:
            logger.info(f"OCR progress: {i + 1}/{page_count} pages")
    
    avg_chars = total_chars / max(page_count, 1)
    logger.info(f"OCR complete: extracted {total_chars} chars from {page_count} pages ({avg_chars:.0f} chars/page)")
    
    return "\n\n".join(all_text), page_count


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS) -> List[str]:
    """
    Split text into chunks of approximately chunk_size characters.
    
    Tries to split on paragraph boundaries, then sentence boundaries.
    """
    chunks = []
    
    # Split into paragraphs
    paragraphs = text.split("\n\n")
    
    current_chunk = []
    current_size = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        para_size = len(para)
        
        # If single paragraph is too large, split by sentences
        if para_size > chunk_size:
            sentences = para.replace(". ", ".\n").split("\n")
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                    
                if current_size + len(sentence) > chunk_size and current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                current_chunk.append(sentence)
                current_size += len(sentence) + 1
        else:
            # Check if adding this paragraph would exceed limit
            if current_size + para_size > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_size = 0
            
            current_chunk.append(para)
            current_size += para_size + 2  # +2 for paragraph break
    
    # Add remaining content
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    # Filter out empty chunks and limit total
    chunks = [c.strip() for c in chunks if c.strip()]
    return chunks[:MAX_CHUNKS_PER_DOCUMENT]


async def check_duplicate(fingerprint: str, file_hash: str, index: str) -> bool:
    """Check if user already uploaded a document with this hash."""
    settings = get_settings()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{settings.search_proxy_url}/documents",
                params={"fingerprint": fingerprint, "index": index},
            )
            response.raise_for_status()
            data = response.json()
            
            for doc in data.get("documents", []):
                if doc.get("file_hash") == file_hash:
                    return True
            return False
    except Exception as e:
        logger.warning(f"Duplicate check failed: {e}")
        return False


async def check_document_limit(fingerprint: str, index: str) -> int:
    """Check how many documents user has uploaded. Returns current count."""
    settings = get_settings()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{settings.search_proxy_url}/documents",
                params={"fingerprint": fingerprint, "index": index},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("total_count", 0)
    except Exception as e:
        logger.warning(f"Document count check failed: {e}")
        return 0


async def index_document_chunks(
    fingerprint: str,
    index: str,
    doc_id: str,
    filename: str,
    chunks: List[str],
    page_count: int,
    file_hash: str,
) -> int:
    """
    Index document chunks via the search proxy.
    
    Returns number of successfully indexed chunks.
    """
    settings = get_settings()
    uploaded_at = datetime.now(timezone.utc).isoformat()
    
    documents = []
    for i, chunk_text in enumerate(chunks):
        chunk_id = f"{doc_id}-chunk{i}"
        
        # Generate embedding
        embedding = await generate_embedding(chunk_text, input_type="document")
        
        doc = {
            "id": chunk_id,
            "title": filename,
            "content": chunk_text,
            "source": "personal",
            "doc_type": "user_upload",
            "citation": f"{filename} (chunk {i + 1}/{len(chunks)})",
            "owner_fingerprint": fingerprint,
            "uploaded_at": uploaded_at,
            "page_count": page_count,
            "file_hash": file_hash,
        }
        
        if embedding:
            doc["embedding"] = embedding
        
        documents.append(doc)
    
    # Send to search proxy
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:  # Longer timeout for many chunks
            response = await client.post(
                f"{settings.search_proxy_url}/index",
                headers={"Content-Type": "application/json"},
                json={
                    "index": index,
                    "fingerprint": fingerprint,
                    "documents": documents,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("indexed_count", 0)
    except Exception as e:
        logger.error(f"Failed to index document chunks: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to index document: {e}")


@router.post("", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    fingerprint: str = Form(...),
    index: str = Form(default="faa-agent"),
):
    """
    Upload a PDF document for indexing.
    
    The document will be:
    1. Validated (size, type)
    2. Checked for duplicates
    3. Text extracted (with OCR fallback)
    4. Chunked and embedded
    5. Indexed via the search proxy
    
    Personal documents are only visible to the user who uploaded them.
    """
    # Validate fingerprint
    if len(fingerprint) < 10:
        raise HTTPException(status_code=400, detail="Invalid fingerprint")
    
    # Validate index
    settings = get_settings()
    valid_indexes = ["faa-agent", "nrc-agent", "dod-agent"]
    if index not in valid_indexes:
        raise HTTPException(status_code=400, detail=f"Invalid index. Must be one of: {valid_indexes}")
    
    # Validate file type
    if file.content_type not in ["application/pdf", "application/x-pdf"]:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Read file content
    content = await file.read()
    
    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400, 
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)} MB"
        )
    
    # Compute file hash for deduplication
    file_hash = compute_file_hash(content)
    
    # Check document limit
    current_count = await check_document_limit(fingerprint, index)
    if current_count >= MAX_DOCUMENTS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Document limit reached. Maximum {MAX_DOCUMENTS_PER_USER} documents allowed."
        )
    
    # Check for duplicate
    if await check_duplicate(fingerprint, file_hash, index):
        raise HTTPException(
            status_code=409,
            detail="Document already uploaded"
        )
    
    # Extract text from PDF
    logger.info(f"Processing PDF: {file.filename} ({len(content)} bytes)")
    
    try:
        full_text, page_count = extract_text_from_pdf(content)
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to process PDF: {e}")
    
    if not full_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from PDF. The file may be image-based or corrupted."
        )
    
    # Chunk text
    chunks = chunk_text(full_text)
    
    if not chunks:
        raise HTTPException(
            status_code=400, 
            detail="No text could be extracted from PDF. This may be a scanned document. Only PDFs with selectable text are supported."
        )
    
    logger.info(f"Extracted {len(full_text)} chars, {len(chunks)} chunks from {page_count} pages")
    
    # Generate document ID
    doc_id = f"{fingerprint[:8]}-{uuid.uuid4().hex[:8]}"
    
    # Index chunks
    indexed_count = await index_document_chunks(
        fingerprint=fingerprint,
        index=index,
        doc_id=doc_id,
        filename=file.filename or "document.pdf",
        chunks=chunks,
        page_count=page_count,
        file_hash=file_hash,
    )
    
    logger.info(f"Indexed {indexed_count} chunks for document {doc_id}")
    
    return DocumentUploadResponse(
        id=doc_id,
        title=file.filename or "document.pdf",
        page_count=page_count,
        chunk_count=indexed_count,
        status="indexed",
    )


@router.get("", response_model=DocumentsListResponse)
async def list_documents(fingerprint: str, index: str = "faa-agent"):
    """List documents uploaded by the user."""
    if len(fingerprint) < 10:
        raise HTTPException(status_code=400, detail="Invalid fingerprint")
    
    settings = get_settings()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{settings.search_proxy_url}/documents",
                params={"fingerprint": fingerprint, "index": index},
            )
            response.raise_for_status()
            data = response.json()
            
            return DocumentsListResponse(
                documents=[DocumentInfo(**doc) for doc in data.get("documents", [])],
                total_count=data.get("total_count", 0),
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to search service")
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/{document_id}")
async def delete_document(document_id: str, fingerprint: str, index: str = "faa-agent"):
    """Delete a user's document and all its chunks."""
    if len(fingerprint) < 10:
        raise HTTPException(status_code=400, detail="Invalid fingerprint")
    
    settings = get_settings()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{settings.search_proxy_url}/documents/{document_id}",
                params={"fingerprint": fingerprint, "index": index},
            )
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Document not found")
            if response.status_code == 403:
                raise HTTPException(status_code=403, detail="Cannot delete document owned by another user")
            
            response.raise_for_status()
            return response.json()
            
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to search service")
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=502, detail=str(e))
