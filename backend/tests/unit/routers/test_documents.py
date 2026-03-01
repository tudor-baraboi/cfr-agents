"""
Unit tests for document upload router (app/routers/documents.py).

Tests cover:
- PDF file upload validation
- Text extraction (digital PDFs)
- Text chunking
- File hash computation
- Document upload flow (with search proxy mocking)
- Document listing
- Document deletion
"""
import pytest
from io import BytesIO
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestDocumentUploadValidation:
    """Tests for POST /documents endpoint validation."""

    def test_upload_missing_file(self, client):
        """Test upload without file parameter."""
        response = client.post(
            "/documents",
            data={"fingerprint": "test-fingerprint-12345"}
            # Missing 'file' parameter
        )
        assert response.status_code == 422

    def test_upload_missing_fingerprint(self, client, sample_pdf_bytes):
        """Test upload without fingerprint."""
        response = client.post(
            "/documents",
            files={"file": ("test.pdf", BytesIO(sample_pdf_bytes), "application/pdf")}
            # Missing 'fingerprint' parameter
        )
        assert response.status_code == 422

    def test_upload_empty_file(self, client):
        """Test upload with empty file."""
        response = client.post(
            "/documents",
            data={"fingerprint": "test-fingerprint-12345"},
            files={"file": ("empty.pdf", BytesIO(b""), "application/pdf")}
        )
        # Should fail - not a valid PDF
        assert response.status_code in [400, 422]

    def test_upload_non_pdf_file(self, client):
        """Test upload with non-PDF file."""
        response = client.post(
            "/documents",
            data={"fingerprint": "test-fingerprint-12345"},
            files={"file": ("test.txt", BytesIO(b"Not a PDF"), "text/plain")}
        )
        assert response.status_code == 400

    def test_upload_short_fingerprint(self, client, sample_pdf_bytes):
        """Test upload with fingerprint shorter than 10 chars."""
        response = client.post(
            "/documents",
            data={"fingerprint": "short"},
            files={"file": ("test.pdf", BytesIO(sample_pdf_bytes), "application/pdf")}
        )
        assert response.status_code == 400

    def test_upload_invalid_index(self, client, sample_pdf_bytes):
        """Test upload with invalid index name."""
        response = client.post(
            "/documents",
            data={"fingerprint": "test-fingerprint-12345", "index": "invalid-index"},
            files={"file": ("test.pdf", BytesIO(sample_pdf_bytes), "application/pdf")}
        )
        assert response.status_code == 400


@pytest.mark.unit
class TestTextExtraction:
    """Tests for text extraction from PDFs."""

    def test_extract_text_from_digital_pdf(self, sample_pdf_bytes):
        """Test text extraction from digital (text-based) PDF."""
        from app.routers.documents import extract_text_from_pdf

        text, page_count = extract_text_from_pdf(sample_pdf_bytes)

        assert isinstance(text, str)
        assert len(text) > 0
        assert page_count == 1
        assert "Test PDF" in text or "Test" in text

    def test_extract_text_empty_pdf(self):
        """Test text extraction from minimal empty PDF."""
        from app.routers.documents import extract_text_from_pdf

        # Minimal valid PDF with no text
        empty_pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
214
%%EOF
"""
        text, page_count = extract_text_from_pdf(empty_pdf)

        assert isinstance(text, str)
        assert page_count == 1


@pytest.mark.unit
class TestTextChunking:
    """Tests for text chunking logic."""

    def test_chunk_single_paragraph(self):
        """Test chunking a single paragraph."""
        from app.routers.documents import chunk_text

        text = "This is a test. " * 100
        chunks = chunk_text(text, chunk_size=500)

        assert isinstance(chunks, list)
        assert len(chunks) > 0
        assert all(isinstance(chunk, str) for chunk in chunks)
        assert all(len(chunk) > 0 for chunk in chunks)

    def test_chunk_multiple_paragraphs(self):
        """Test chunking text with multiple paragraphs."""
        from app.routers.documents import chunk_text

        text = "\n\n".join([
            "Paragraph 1. " * 100,
            "Paragraph 2. " * 100,
            "Paragraph 3. " * 100,
        ])
        chunks = chunk_text(text, chunk_size=1000)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 2000  # Roughly chunk_size

    def test_chunk_empty_text(self):
        """Test chunking empty text."""
        from app.routers.documents import chunk_text

        chunks = chunk_text("", chunk_size=1000)
        assert isinstance(chunks, list)
        assert len(chunks) <= 1

    def test_chunk_very_small_text(self):
        """Test chunking text smaller than chunk size."""
        from app.routers.documents import chunk_text

        text = "Short text"
        chunks = chunk_text(text, chunk_size=1000)

        assert len(chunks) == 1
        assert chunks[0] == text


@pytest.mark.unit
class TestDocumentMetadata:
    """Tests for document metadata handling."""

    def test_compute_file_hash(self, sample_pdf_bytes):
        """Test SHA-256 hash computation."""
        from app.routers.documents import compute_file_hash

        hash1 = compute_file_hash(sample_pdf_bytes)
        hash2 = compute_file_hash(sample_pdf_bytes)

        # Same content should produce same hash
        assert hash1 == hash2
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 hex is 64 chars

    def test_file_hash_changes_with_content(self, sample_pdf_bytes):
        """Test that different content produces different hashes."""
        from app.routers.documents import compute_file_hash

        hash1 = compute_file_hash(sample_pdf_bytes)
        hash2 = compute_file_hash(sample_pdf_bytes + b"extra")

        assert hash1 != hash2


def _make_httpx_mock(get_response=None, post_response=None, delete_response=None):
    """
    Create properly mocked httpx.AsyncClient for context manager usage.
    
    httpx.AsyncClient uses async context manager, but response methods
    like .json() and .raise_for_status() are synchronous.
    """
    mock_client = AsyncMock()

    if get_response is not None:
        resp = MagicMock()
        resp.status_code = get_response.get("status_code", 200)
        resp.json.return_value = get_response.get("json", {})
        resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=resp)

    if post_response is not None:
        resp = MagicMock()
        resp.status_code = post_response.get("status_code", 200)
        resp.json.return_value = post_response.get("json", {})
        resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=resp)

    if delete_response is not None:
        resp = MagicMock()
        resp.status_code = delete_response.get("status_code", 200)
        resp.json.return_value = delete_response.get("json", {})
        resp.raise_for_status = MagicMock()
        mock_client.delete = AsyncMock(return_value=resp)

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    return mock_client


@pytest.mark.unit
class TestDocumentUploadFlow:
    """Integration-style tests for the complete upload flow."""

    @patch("app.routers.documents.generate_embeddings_batch")
    @patch("app.routers.documents.extract_text_from_pdf")
    @patch("httpx.AsyncClient")
    def test_successful_upload(self, mock_httpx_cls, mock_extract, mock_embeddings, client, sample_pdf_bytes):
        """Full upload flow: validate, extract, chunk, embed, index."""
        mock_extract.return_value = ("Sample extracted text from PDF document " * 10, 1)
        mock_embeddings.return_value = [[0.1] * 1024]

        # Mock search proxy: check_document_limit, check_duplicate, index
        # The endpoint makes multiple httpx calls: GET (limit check), GET (dup check), POST (index)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        # GET /documents for limit check and duplicate check
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"documents": [], "total_count": 0}
        get_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=get_resp)

        # POST /index for indexing
        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"indexed_count": 1}
        post_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=post_resp)

        mock_httpx_cls.return_value = mock_client

        response = client.post(
            "/documents",
            data={"fingerprint": "test-fingerprint-12345"},
            files={"file": ("test.pdf", BytesIO(sample_pdf_bytes), "application/pdf")}
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] == "indexed"
        assert data["page_count"] == 1

    @patch("app.routers.documents.generate_embeddings_batch")
    @patch("app.routers.documents.extract_text_from_pdf")
    @patch("httpx.AsyncClient")
    def test_upload_duplicate_rejected(self, mock_httpx_cls, mock_extract, mock_embeddings, client, sample_pdf_bytes):
        """Upload of duplicate document returns 409."""
        mock_extract.return_value = ("Some text", 1)

        # Mock search proxy returns existing doc with same hash
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        from app.routers.documents import compute_file_hash
        file_hash = compute_file_hash(sample_pdf_bytes)

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {
            "documents": [{"file_hash": file_hash, "id": "existing"}],
            "total_count": 1
        }
        get_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=get_resp)

        mock_httpx_cls.return_value = mock_client

        response = client.post(
            "/documents",
            data={"fingerprint": "test-fingerprint-12345"},
            files={"file": ("test.pdf", BytesIO(sample_pdf_bytes), "application/pdf")}
        )
        assert response.status_code == 409


@pytest.mark.unit
class TestDocumentListing:
    """Tests for GET /documents endpoint."""

    def test_list_documents_no_fingerprint(self, client):
        """Missing fingerprint query param returns 422."""
        response = client.get("/documents")
        assert response.status_code == 422

    def test_list_documents_short_fingerprint(self, client):
        """Short fingerprint returns 400."""
        response = client.get("/documents", params={"fingerprint": "short"})
        assert response.status_code == 400

    @patch("httpx.AsyncClient")
    def test_list_documents_empty(self, mock_httpx_cls, client):
        """User with no documents gets empty list."""
        mock_client = _make_httpx_mock(
            get_response={"json": {"documents": [], "total_count": 0}}
        )
        mock_httpx_cls.return_value = mock_client

        response = client.get(
            "/documents",
            params={"fingerprint": "test-fingerprint-12345"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["documents"] == []
        assert data["total_count"] == 0

    @patch("httpx.AsyncClient")
    def test_list_documents_with_results(self, mock_httpx_cls, client):
        """User with documents gets them listed."""
        mock_client = _make_httpx_mock(
            get_response={
                "json": {
                    "documents": [
                        {
                            "id": "doc-1",
                            "title": "Test Document",
                            "filename": "test.pdf",
                            "uploaded_at": "2026-02-17T00:00:00Z",
                            "chunk_count": 10,
                        }
                    ],
                    "total_count": 1,
                }
            }
        )
        mock_httpx_cls.return_value = mock_client

        response = client.get(
            "/documents",
            params={"fingerprint": "test-fingerprint-12345"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) == 1
        assert data["documents"][0]["id"] == "doc-1"
        assert data["total_count"] == 1


@pytest.mark.unit
class TestDocumentDeletion:
    """Tests for DELETE /documents/{document_id} endpoint."""

    def test_delete_no_fingerprint(self, client):
        """Missing fingerprint query param returns 422."""
        response = client.delete("/documents/fake-doc-id")
        assert response.status_code == 422

    def test_delete_short_fingerprint(self, client):
        """Short fingerprint returns 400."""
        response = client.delete(
            "/documents/fake-doc-id",
            params={"fingerprint": "short"}
        )
        assert response.status_code == 400

    @patch("httpx.AsyncClient")
    def test_delete_not_found(self, mock_httpx_cls, client):
        """Deleting non-existent document returns 404."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        resp = MagicMock()
        resp.status_code = 404
        mock_client.delete = AsyncMock(return_value=resp)
        mock_httpx_cls.return_value = mock_client

        response = client.delete(
            "/documents/nonexistent-doc-id",
            params={"fingerprint": "test-fingerprint-12345"}
        )
        assert response.status_code == 404

    @patch("httpx.AsyncClient")
    def test_delete_success(self, mock_httpx_cls, client):
        """Successful deletion returns proxy response."""
        mock_client = _make_httpx_mock(
            delete_response={"json": {"deleted": True, "chunks_removed": 5}}
        )
        mock_httpx_cls.return_value = mock_client

        response = client.delete(
            "/documents/doc-123",
            params={"fingerprint": "test-fingerprint-12345"}
        )
        assert response.status_code == 200

    @patch("httpx.AsyncClient")
    def test_delete_wrong_owner(self, mock_httpx_cls, client):
        """Deleting another user's document returns 403."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        resp = MagicMock()
        resp.status_code = 403
        mock_client.delete = AsyncMock(return_value=resp)
        mock_httpx_cls.return_value = mock_client

        response = client.delete(
            "/documents/other-users-doc",
            params={"fingerprint": "test-fingerprint-12345"}
        )
        assert response.status_code == 403


@pytest.mark.unit
class TestDocumentEmbedding:
    """Tests for embedding-related fixtures."""

    def test_embedding_vector_dimension(self, mock_embeddings_response):
        """Test that mock embeddings have correct dimension."""
        embedding = mock_embeddings_response["data"][0]["embedding"]
        assert isinstance(embedding, list)
        assert len(embedding) == 1024
