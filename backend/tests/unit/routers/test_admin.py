"""
Unit tests for admin router endpoints.

Tests the admin.py router which provides:
- GET /admin/usage - list all usage records (requires admin auth)
- GET /admin/feedback - list all feedback records (requires admin auth)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Test client."""
    return TestClient(app)


# ================================
# Test Authorization
# ================================

class TestAdminAuthorization:
    """Test admin endpoint authorization checks."""

    def test_usage_no_auth_header(self, client):
        """GET /admin/usage without Authorization header returns 401."""
        response = client.get("/admin/usage")
        assert response.status_code == 401

    def test_usage_invalid_token(self, client):
        """GET /admin/usage with invalid JWT returns 401."""
        response = client.get(
            "/admin/usage",
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401

    def test_usage_non_admin_token(self, client, valid_jwt_token):
        """GET /admin/usage with non-admin token returns 403."""
        response = client.get(
            "/admin/usage",
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        assert response.status_code == 403

    def test_feedback_no_auth_header(self, client):
        """GET /admin/feedback without Authorization header returns 401."""
        response = client.get("/admin/feedback")
        assert response.status_code == 401

    def test_feedback_invalid_token(self, client):
        """GET /admin/feedback with invalid JWT returns 401."""
        response = client.get(
            "/admin/feedback",
            headers={"Authorization": "Bearer bad-token"}
        )
        assert response.status_code == 401

    def test_feedback_non_admin_token(self, client, valid_jwt_token):
        """GET /admin/feedback with non-admin token returns 403."""
        response = client.get(
            "/admin/feedback",
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        assert response.status_code == 403


# ================================
# Test GET /admin/usage
# ================================

class TestAdminUsage:
    """Test the GET /admin/usage endpoint."""

    @patch("app.routers.admin.get_usage_tracker")
    def test_get_usage_success(self, mock_get_tracker, client, admin_jwt_token):
        """Admin can list all usage records."""
        mock_tracker = MagicMock()
        mock_tracker.list_all_usage = AsyncMock(return_value=[
            {
                "date": "2026-02-17",
                "fingerprint": "abc12345-test",
                "request_count": 5,
                "first_request_at": "2026-02-17T10:00:00Z",
                "last_request_at": "2026-02-17T12:00:00Z",
                "user_agent": "Mozilla/5.0",
                "ip_address": "1.2.3.4",
                "country": "US",
                "city": "San Francisco",
            }
        ])
        mock_get_tracker.return_value = mock_tracker

        response = client.get(
            "/admin/usage",
            headers={"Authorization": f"Bearer {admin_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "usage" in data
        assert len(data["usage"]) == 1
        assert data["usage"][0]["date"] == "2026-02-17"
        assert data["usage"][0]["request_count"] == 5

    @patch("app.routers.admin.get_usage_tracker")
    def test_get_usage_empty(self, mock_get_tracker, client, admin_jwt_token):
        """Admin gets empty list when no usage records exist."""
        mock_tracker = MagicMock()
        mock_tracker.list_all_usage = AsyncMock(return_value=[])
        mock_get_tracker.return_value = mock_tracker

        response = client.get(
            "/admin/usage",
            headers={"Authorization": f"Bearer {admin_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["usage"] == []


# ================================
# Test GET /admin/feedback
# ================================

class TestAdminFeedback:
    """Test the GET /admin/feedback endpoint."""

    @patch("app.routers.admin.get_feedback_service")
    def test_get_feedback_success(self, mock_get_service, client, admin_jwt_token):
        """Admin can list all feedback records."""
        mock_service = MagicMock()
        mock_service.list_all_feedback = AsyncMock(return_value=[
            {
                "id": "fb-001",
                "date": "2026-02-17",
                "type": "bug",
                "message": "Search is slow",
                "fingerprint": "abc12345",
                "logs_url": "https://blob/feedback-logs/2026-02-17/fb-001.json",
                "user_agent": "Mozilla/5.0",
                "created_at": "2026-02-17T14:00:00Z",
                "contact": {"name": "Alice", "email": "alice@example.com"},
            }
        ])
        mock_get_service.return_value = mock_service

        response = client.get(
            "/admin/feedback",
            headers={"Authorization": f"Bearer {admin_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "feedback" in data
        assert len(data["feedback"]) == 1
        assert data["feedback"][0]["type"] == "bug"

    @patch("app.routers.admin.get_feedback_service")
    def test_get_feedback_empty(self, mock_get_service, client, admin_jwt_token):
        """Admin gets empty list when no feedback exists."""
        mock_service = MagicMock()
        mock_service.list_all_feedback = AsyncMock(return_value=[])
        mock_get_service.return_value = mock_service

        response = client.get(
            "/admin/feedback",
            headers={"Authorization": f"Bearer {admin_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["feedback"] == []
