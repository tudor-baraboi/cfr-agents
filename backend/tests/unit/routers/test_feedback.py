"""
Unit tests for feedback router endpoints.

Tests the feedback.py router which provides:
- POST /feedback/submit - submit user feedback with logs
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
# Test POST /feedback/submit
# ================================

class TestFeedbackSubmission:
    """Test feedback submission endpoint."""

    @patch("app.routers.feedback.get_feedback_service")
    def test_submit_feedback_success(self, mock_get_service, client, valid_jwt_token):
        """Authenticated user can submit feedback."""
        mock_service = MagicMock()
        mock_service.submit_feedback = AsyncMock(return_value="fb-uuid-123")
        mock_get_service.return_value = mock_service

        response = client.post(
            "/feedback/submit",
            json={
                "type": "bug",
                "message": "Search is slow when querying CFR sections",
                "logs": [{"level": "error", "msg": "timeout"}],
                "userAgent": "Mozilla/5.0",
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "fb-uuid-123"
        assert "message" in data
        mock_service.submit_feedback.assert_called_once()

    @patch("app.routers.feedback.get_feedback_service")
    def test_submit_feedback_with_contact(self, mock_get_service, client, valid_jwt_token):
        """Feedback can include optional contact info."""
        mock_service = MagicMock()
        mock_service.submit_feedback = AsyncMock(return_value="fb-uuid-456")
        mock_get_service.return_value = mock_service

        response = client.post(
            "/feedback/submit",
            json={
                "type": "feature",
                "message": "Please add NRC document search",
                "logs": [],
                "userAgent": "Mozilla/5.0",
                "contact": {
                    "name": "Alice",
                    "email": "alice@example.com",
                    "company": "Aerospace Inc",
                },
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "fb-uuid-456"

    def test_submit_feedback_no_auth(self, client):
        """Feedback requires authentication."""
        response = client.post(
            "/feedback/submit",
            json={
                "type": "bug",
                "message": "Something broke",
            },
        )
        assert response.status_code == 401

    def test_submit_feedback_invalid_type(self, client, valid_jwt_token):
        """Feedback type must be bug, feature, or other."""
        response = client.post(
            "/feedback/submit",
            json={
                "type": "invalid_type",
                "message": "Testing invalid type",
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        assert response.status_code == 400

    def test_submit_feedback_empty_message(self, client, valid_jwt_token):
        """Feedback message cannot be empty."""
        response = client.post(
            "/feedback/submit",
            json={
                "type": "bug",
                "message": "   ",
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        assert response.status_code == 400

    def test_submit_feedback_missing_message(self, client, valid_jwt_token):
        """Feedback must include a message field."""
        response = client.post(
            "/feedback/submit",
            json={
                "type": "bug",
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        assert response.status_code == 422

    def test_submit_feedback_missing_type(self, client, valid_jwt_token):
        """Feedback must include a type field."""
        response = client.post(
            "/feedback/submit",
            json={
                "message": "No type provided",
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        assert response.status_code == 422

    @patch("app.routers.feedback.get_feedback_service")
    def test_submit_feedback_type_other(self, mock_get_service, client, valid_jwt_token):
        """Feedback type 'other' is accepted."""
        mock_service = MagicMock()
        mock_service.submit_feedback = AsyncMock(return_value="fb-other")
        mock_get_service.return_value = mock_service

        response = client.post(
            "/feedback/submit",
            json={
                "type": "other",
                "message": "General comment about the system",
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        assert response.status_code == 200

    @patch("app.routers.feedback.get_feedback_service")
    def test_submit_feedback_with_empty_logs(self, mock_get_service, client, valid_jwt_token):
        """Feedback with empty logs array is valid."""
        mock_service = MagicMock()
        mock_service.submit_feedback = AsyncMock(return_value="fb-nologs")
        mock_get_service.return_value = mock_service

        response = client.post(
            "/feedback/submit",
            json={
                "type": "bug",
                "message": "No logs to attach",
                "logs": [],
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        assert response.status_code == 200

    def test_submit_feedback_expired_token(self, client, expired_jwt_token):
        """Expired token is rejected."""
        response = client.post(
            "/feedback/submit",
            json={
                "type": "bug",
                "message": "Token expired",
            },
            headers={"Authorization": f"Bearer {expired_jwt_token}"}
        )
        assert response.status_code == 401
