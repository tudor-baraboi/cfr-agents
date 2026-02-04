"""
Shared test fixtures for pytest.

This module provides reusable fixtures for mocking Azure services,
external APIs, and other dependencies.
"""
import pytest
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from typing import AsyncGenerator

# Set test environment variables before importing app
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "test-secret-key-for-unit-tests-only"
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
os.environ["AZURE_BLOB_CONNECTION_STRING"] = "DefaultEndpointsProtocol=https;AccountName=test;AccountKey=testkey==;EndpointSuffix=core.windows.net"
os.environ["AZURE_SEARCH_ENDPOINT"] = "https://test-search.search.windows.net"
os.environ["AZURE_SEARCH_KEY"] = "test-search-key"
os.environ["AZURE_AI_SERVICES_ENDPOINT"] = "https://test-ai.cognitiveservices.azure.com"
os.environ["AZURE_AI_SERVICES_KEY"] = "test-ai-key"
os.environ["SEARCH_PROXY_URL"] = "http://localhost:8001"
os.environ["ADMIN_CODES"] = "TEST-ADMIN-123,CASESENSITIVE123,ADMIN-123"

from app.main import app
from app.config import get_settings, Settings


@pytest.fixture
def test_settings() -> Settings:
    """Override settings for tests."""
    return get_settings()


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_azure_blob():
    """Mock Azure Blob Storage client."""
    with patch("azure.storage.blob.BlobServiceClient") as mock:
        blob_client = MagicMock()
        blob_client.upload_blob = AsyncMock()
        blob_client.download_blob = AsyncMock()
        blob_client.exists = AsyncMock(return_value=False)
        
        container_client = MagicMock()
        container_client.get_blob_client.return_value = blob_client
        container_client.list_blobs = MagicMock(return_value=[])
        
        mock.from_connection_string.return_value.get_container_client.return_value = container_client
        yield mock


@pytest.fixture
def mock_azure_table():
    """Mock Azure Table Storage client."""
    with patch("azure.data.tables.TableServiceClient") as mock:
        table_client = MagicMock()
        table_client.create_entity = AsyncMock()
        table_client.get_entity = AsyncMock()
        table_client.update_entity = AsyncMock()
        table_client.upsert_entity = AsyncMock()
        table_client.query_entities = AsyncMock(return_value=[])
        table_client.delete_entity = AsyncMock()
        
        mock.from_connection_string.return_value.get_table_client.return_value = table_client
        yield mock


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient for external API calls."""
    with patch("httpx.AsyncClient") as mock:
        response = AsyncMock()
        response.status_code = 200
        response.text = ""
        response.json.return_value = {}
        response.raise_for_status = MagicMock()
        
        client = AsyncMock()
        client.get.return_value = response
        client.post.return_value = response
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        
        mock.return_value = client
        yield mock


@pytest.fixture
def mock_claude_client():
    """Mock Anthropic Claude API client."""
    with patch("anthropic.AsyncAnthropic") as mock:
        # Mock streaming response
        stream_mock = AsyncMock()
        
        # Create async iterator for stream events
        async def mock_stream():
            yield MagicMock(type="message_start")
            yield MagicMock(
                type="content_block_delta",
                delta=MagicMock(type="text_delta", text="Test response")
            )
            yield MagicMock(type="message_stop")
        
        stream_mock.__aiter__ = mock_stream
        
        messages_mock = MagicMock()
        messages_mock.stream.return_value.__aenter__.return_value = stream_mock
        
        client_instance = MagicMock()
        client_instance.messages = messages_mock
        
        mock.return_value = client_instance
        yield mock


@pytest.fixture
def valid_jwt_token(test_settings) -> str:
    """Generate a valid JWT token for testing."""
    from jose import jwt
    from datetime import datetime, timedelta, timezone
    
    payload = {
        "fingerprint": "test-fingerprint-123",
        "is_admin": False,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, test_settings.jwt_secret, algorithm="HS256")


@pytest.fixture
def admin_jwt_token(test_settings) -> str:
    """Generate an admin JWT token for testing."""
    from jose import jwt
    from datetime import datetime, timedelta, timezone
    
    payload = {
        "fingerprint": "admin-fingerprint-456",
        "is_admin": True,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, test_settings.jwt_secret, algorithm="HS256")


@pytest.fixture
def expired_jwt_token(test_settings) -> str:
    """Generate an expired JWT token for testing."""
    from jose import jwt
    from datetime import datetime, timedelta, timezone
    
    payload = {
        "fingerprint": "test-fingerprint-789",
        "is_admin": False,
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
    }
    return jwt.encode(payload, test_settings.jwt_secret, algorithm="HS256")


@pytest.fixture
def sample_usage_entity() -> dict:
    """Sample usage entity from Azure Tables."""
    return {
        "PartitionKey": "2026-02-02",
        "RowKey": "test-fingerprint-123",
        "requests_used": 5,
        "daily_limit": 15,
        "first_request": datetime.now(timezone.utc).isoformat(),
        "last_request": datetime.now(timezone.utc).isoformat(),
        "country": "US",
        "region": "California",
        "city": "San Francisco",
    }


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Sample PDF file bytes (minimal valid PDF)."""
    # Minimal valid PDF structure
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000317 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
408
%%EOF
"""


@pytest.fixture
async def test_db():
    """In-memory SQLite database for testing."""
    import aiosqlite
    from app.database import init_db
    
    # Use in-memory database
    db_path = ":memory:"
    
    # Initialize schema
    await init_db(db_path)
    
    # Connect for tests
    async with aiosqlite.connect(db_path) as db:
        yield db


@pytest.fixture
def mock_embeddings_response():
    """Mock response from Azure AI Services embeddings API."""
    return {
        "data": [
            {
                "embedding": [0.1] * 1024,  # 1024-dimensional vector
                "index": 0
            }
        ]
    }
