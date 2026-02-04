"""
Shared fixtures and configuration for integration tests.

Provides:
- Real database connections (test database)
- Real WebSocket client setup
- Real API credential mocking
- Test data seeding
- Cleanup fixtures
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Generator, AsyncGenerator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient
import json
import os

from app.main import app
from app.database import Base, get_db
from app.config import get_settings


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def test_database_url():
    """
    Provide test database URL.
    
    Uses SQLite in-memory database for fast isolated tests.
    Falls back to PostgreSQL test database if TESTING_DATABASE_URL is set.
    """
    test_db_url = os.getenv("TESTING_DATABASE_URL")
    if test_db_url:
        return test_db_url
    
    # Use SQLite for fast, isolated tests
    return "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine(test_database_url):
    """Create database engine for test database."""
    if test_database_url.startswith("sqlite"):
        engine = create_engine(
            test_database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        # PostgreSQL
        engine = create_engine(
            test_database_url,
            echo=False,
            pool_pre_ping=True,
        )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    yield engine
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="session")
def SessionLocal(engine):
    """Create session factory for test database."""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session(SessionLocal) -> Generator[Session, None, None]:
    """
    Provide a database session for each test.
    
    Automatically rolls back after test to maintain isolation.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def override_get_db(db_session):
    """Override get_db dependency for FastAPI."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass
    return _override_get_db


# ============================================================================
# HTTP CLIENT FIXTURES
# ============================================================================

@pytest.fixture
def client(override_get_db):
    """
    Provide TestClient with overridden database dependency.
    
    This allows tests to run with a real FastAPI app but isolated database.
    """
    app.dependency_overrides[get_db] = override_get_db
    
    from fastapi.testclient import TestClient
    with TestClient(app) as test_client:
        yield test_client
    
    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(override_get_db):
    """
    Provide AsyncClient for WebSocket tests.
    
    Allows testing async WebSocket connections with isolated database.
    """
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Cleanup
    app.dependency_overrides.clear()


# ============================================================================
# AUTHENTICATION FIXTURES
# ============================================================================

@pytest.fixture
def test_user_fingerprint():
    """Provide a test user fingerprint."""
    return "test_fingerprint_12345abcde"


@pytest.fixture
def test_user_token():
    """Provide a test JWT token."""
    from datetime import datetime, timedelta
    from jose import jwt
    
    # Create a valid JWT token
    payload = {
        "sub": "test_fingerprint_12345abcde",
        "fingerprint": "test_fingerprint_12345abcde",
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }
    
    secret = os.getenv("JWT_SECRET_KEY", "test-secret-key")
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token


@pytest.fixture
def test_admin_token():
    """Provide a test admin JWT token."""
    from datetime import datetime, timedelta
    from jose import jwt
    
    # Create a valid JWT token with admin role
    payload = {
        "sub": "admin_user",
        "fingerprint": "admin_fingerprint",
        "role": "admin",
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }
    
    secret = os.getenv("JWT_SECRET_KEY", "test-secret-key")
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token


@pytest.fixture
def auth_headers(test_user_token):
    """Provide authorization headers with test token."""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def admin_auth_headers(test_admin_token):
    """Provide authorization headers with admin token."""
    return {"Authorization": f"Bearer {test_admin_token}"}


# ============================================================================
# TEST DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_cfr_section():
    """Provide sample CFR section data."""
    return {
        "title": "§ 25.1317 - High-Intensity Radiated Fields (HIRF) Protection",
        "section": "25.1317",
        "part": "25",
        "content": """
        (a) General. Each electrical and electronic system must be designed 
        and installed to ensure safe operation without loss of function under 
        the conditions of High-Intensity Radiated Fields (HIRF) protection.
        
        (b) HIRF environment and equipment. The HIRF environment is defined 
        in Appendix J. Equipment used in civil aviation must be designed to 
        protect against the HIRF environment defined in that appendix.
        
        (c) Testing. Equipment must be tested to demonstrate that it can 
        withstand exposure to the HIRF environment without degradation beyond 
        the limits specified in technical standards.
        """,
        "url": "https://www.ecfr.gov/current/title-14/section-25.1317",
    }


@pytest.fixture
def sample_conversation_message():
    """Provide sample conversation message."""
    return {
        "type": "user",
        "content": "What are the HIRF protection requirements for aircraft electrical systems?",
        "timestamp": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def sample_feedback():
    """Provide sample feedback data."""
    return {
        "rating": 5,
        "feedback_text": "Very accurate and comprehensive response.",
        "tags": ["accurate", "helpful", "detailed"],
    }


@pytest.fixture
def sample_trial_code():
    """Provide sample trial code data."""
    return {
        "code": "TRIAL2026",
        "max_tokens": 100000,
        "max_users": 50,
        "expiry_date": (datetime.utcnow() + timedelta(days=30)).date().isoformat(),
    }


# ============================================================================
# API MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_ecfr_response():
    """Provide mock eCFR API response."""
    return {
        "results": [
            {
                "title": "§ 25.1317 - HIRF Protection",
                "full_text": "Sample HIRF requirement text...",
                "reserved": False,
                "structure": {
                    "part": "25",
                    "section": "1317",
                }
            }
        ],
        "count": 1,
        "total_count": 1,
    }


@pytest.fixture
def mock_drs_response():
    """Provide mock DRS API response."""
    return {
        "summary": {
            "doctypeName": "AC",
            "drsDoctypeName": "Advisory Circulars (AC)",
            "count": 10,
            "hasMoreItems": False,
            "totalItems": 10,
        },
        "documents": [
            {
                "documentNumber": "AC 25-7A",
                "title": "HIRF Protection for Aircraft Systems",
                "documentGuid": "doc-guid-123",
                "documentURL": "https://drs.faa.gov/document/123",
                "drs:status": ["Current"],
            }
        ]
    }


@pytest.fixture
def mock_azure_search_response():
    """Provide mock Azure AI Search response."""
    return {
        "@odata.count": 5,
        "value": [
            {
                "id": "hirf-protection-1",
                "title": "HIRF Protection in 14 CFR Part 25",
                "content": "High-Intensity Radiated Fields protection requirements...",
                "section": "25.1317",
                "source_type": "CFR",
                "@search.score": 8.5,
            }
        ]
    }


# ============================================================================
# CLEANUP FIXTURES
# ============================================================================

@pytest.fixture
def cleanup_test_data(db_session):
    """
    Cleanup test data after each test.
    
    Ensures test isolation by clearing all tables.
    """
    yield
    
    # Rollback any remaining transactions
    db_session.rollback()


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset app state between tests."""
    yield
    
    # Clear any app-level state
    app.dependency_overrides.clear()


# ============================================================================
# EVENT LOOP FIXTURE
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def async_client_ws(async_client, test_user_token):
    """
    Provide async client configured for WebSocket testing.
    
    Pre-configured with authentication headers.
    """
    async_client.headers.update({
        "Authorization": f"Bearer {test_user_token}"
    })
    return async_client


# ============================================================================
# HELPER FIXTURES
# ============================================================================

@pytest.fixture
def fake_datetime():
    """Provide controlled datetime for testing."""
    class FakeDatetime:
        @staticmethod
        def now():
            return datetime(2026, 2, 1, 12, 0, 0)
        
        @staticmethod
        def utcnow():
            return datetime(2026, 2, 1, 12, 0, 0)
    
    return FakeDatetime()


@pytest.fixture
def assert_valid_response():
    """Provide helper to validate API response structure."""
    def _assert_valid_response(response, expected_status=200):
        assert response.status_code == expected_status, \
            f"Expected {expected_status}, got {response.status_code}: {response.text}"
        
        # Try to parse JSON
        try:
            data = response.json()
            return data
        except ValueError:
            pytest.fail(f"Response is not valid JSON: {response.text}")
    
    return _assert_valid_response


@pytest.fixture
def assert_websocket_message():
    """Provide helper to validate WebSocket message structure."""
    def _assert_valid_message(message, expected_type=None):
        assert isinstance(message, dict), f"Message should be dict, got {type(message)}"
        assert "type" in message, "Message missing 'type' field"
        
        if expected_type:
            assert message["type"] == expected_type, \
                f"Expected type {expected_type}, got {message['type']}"
        
        return message
    
    return _assert_valid_message
