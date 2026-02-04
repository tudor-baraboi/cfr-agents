"""
Unit tests for feedback system router endpoints.

Tests the feedback.py router which provides endpoints for:
- User feedback submission
- Conversation rating
- Response quality metrics
- Feedback data persistence
- Aggregate statistics
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.routers import feedback


# Mock get_db for dependency override
def get_db():
    """Mock database dependency."""
    pass


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    db.execute = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.close = MagicMock()
    return db


@pytest.fixture
def client(mock_db):
    """Test client with mocked database."""
    def override_get_db():
        try:
            yield mock_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_token():
    """Mock authentication token."""
    return "user_jwt_token_here"


@pytest.fixture
def sample_feedback():
    """Sample feedback data for testing."""
    return {
        "conversation_id": "conv_123",
        "message_id": "msg_456",
        "rating": 5,
        "feedback_text": "Very helpful response!",
        "tags": ["accurate", "fast", "comprehensive"]
    }


# ================================
# Test Feedback Submission
# ================================

class TestFeedbackSubmission:
    """Test suite for feedback submission endpoints."""
    
    def test_submit_feedback_success(self, client, mock_db, auth_token, sample_feedback):
        """Test successful feedback submission."""
        response = client.post(
            "/api/feedback",
            json=sample_feedback,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert "feedback_id" in data
        mock_db.commit.assert_called_once()
    
    def test_submit_feedback_minimal_data(self, client, mock_db, auth_token):
        """Test feedback submission with only required fields."""
        minimal_feedback = {
            "conversation_id": "conv_123",
            "rating": 4
        }
        
        response = client.post(
            "/api/feedback",
            json=minimal_feedback,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 201
        mock_db.commit.assert_called_once()
    
    def test_submit_feedback_invalid_rating(self, client, mock_db, auth_token):
        """Test feedback submission with invalid rating value."""
        invalid_feedback = {
            "conversation_id": "conv_123",
            "rating": 6  # Rating should be 1-5
        }
        
        response = client.post(
            "/api/feedback",
            json=invalid_feedback,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 422
    
    def test_submit_feedback_missing_required_fields(self, client, mock_db, auth_token):
        """Test feedback submission with missing required fields."""
        incomplete_feedback = {
            "feedback_text": "Great response!"
            # Missing conversation_id and rating
        }
        
        response = client.post(
            "/api/feedback",
            json=incomplete_feedback,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 422
    
    def test_submit_feedback_unauthorized(self, client, mock_db):
        """Test feedback submission without authentication."""
        feedback_data = {
            "conversation_id": "conv_123",
            "rating": 5
        }
        
        response = client.post(
            "/api/feedback",
            json=feedback_data
        )
        
        assert response.status_code == 401
    
    def test_submit_feedback_with_tags(self, client, mock_db, auth_token):
        """Test feedback submission with custom tags."""
        feedback_with_tags = {
            "conversation_id": "conv_123",
            "rating": 5,
            "tags": ["helpful", "accurate", "detailed", "fast"]
        }
        
        response = client.post(
            "/api/feedback",
            json=feedback_with_tags,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 201
        mock_db.commit.assert_called_once()


# ================================
# Test Response Rating
# ================================

class TestResponseRating:
    """Test suite for rating individual responses."""
    
    def test_rate_response_thumbs_up(self, client, mock_db, auth_token):
        """Test giving a thumbs up to a response."""
        rating_data = {
            "message_id": "msg_456",
            "rating_type": "thumbs_up"
        }
        
        response = client.post(
            "/api/feedback/rate",
            json=rating_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["rating_type"] == "thumbs_up"
        mock_db.commit.assert_called_once()
    
    def test_rate_response_thumbs_down(self, client, mock_db, auth_token):
        """Test giving a thumbs down to a response."""
        rating_data = {
            "message_id": "msg_456",
            "rating_type": "thumbs_down",
            "reason": "Incomplete answer"
        }
        
        response = client.post(
            "/api/feedback/rate",
            json=rating_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        mock_db.commit.assert_called_once()
    
    def test_update_existing_rating(self, client, mock_db, auth_token):
        """Test updating an existing rating."""
        # First rating
        first_rating = {
            "message_id": "msg_456",
            "rating_type": "thumbs_up"
        }
        
        response1 = client.post(
            "/api/feedback/rate",
            json=first_rating,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response1.status_code == 200
        
        # Update rating
        updated_rating = {
            "message_id": "msg_456",
            "rating_type": "thumbs_down",
            "reason": "Changed my mind"
        }
        
        response2 = client.post(
            "/api/feedback/rate",
            json=updated_rating,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response2.status_code == 200
    
    def test_get_message_rating_stats(self, client, mock_db, auth_token):
        """Test fetching rating statistics for a message."""
        message_id = "msg_456"
        
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (15, 3)  # 15 thumbs up, 3 thumbs down
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            f"/api/feedback/message/{message_id}/stats",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["thumbs_up"] == 15
        assert data["thumbs_down"] == 3


# ================================
# Test Quality Metrics
# ================================

class TestQualityMetrics:
    """Test suite for response quality metrics."""
    
    def test_track_response_accuracy(self, client, mock_db, auth_token):
        """Test tracking response accuracy metric."""
        accuracy_data = {
            "message_id": "msg_456",
            "accuracy_score": 0.95,
            "user_corrected": False
        }
        
        response = client.post(
            "/api/feedback/quality/accuracy",
            json=accuracy_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        mock_db.commit.assert_called_once()
    
    def test_track_response_completeness(self, client, mock_db, auth_token):
        """Test tracking response completeness metric."""
        completeness_data = {
            "message_id": "msg_456",
            "completeness_score": 0.85,
            "missing_info": ["specific examples", "references"]
        }
        
        response = client.post(
            "/api/feedback/quality/completeness",
            json=completeness_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        mock_db.commit.assert_called_once()
    
    def test_track_response_relevance(self, client, mock_db, auth_token):
        """Test tracking response relevance metric."""
        relevance_data = {
            "message_id": "msg_456",
            "relevance_score": 0.90,
            "on_topic": True
        }
        
        response = client.post(
            "/api/feedback/quality/relevance",
            json=relevance_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        mock_db.commit.assert_called_once()
    
    def test_get_conversation_quality_metrics(self, client, mock_db, auth_token):
        """Test fetching quality metrics for entire conversation."""
        conversation_id = "conv_123"
        
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (0.92, 0.88, 0.95)  # avg accuracy, completeness, relevance
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            f"/api/feedback/quality/conversation/{conversation_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["average_accuracy"] == 0.92
        assert data["average_completeness"] == 0.88
        assert data["average_relevance"] == 0.95


# ================================
# Test Feedback Retrieval
# ================================

class TestFeedbackRetrieval:
    """Test suite for retrieving feedback data."""
    
    def test_get_conversation_feedback(self, client, mock_db, auth_token):
        """Test fetching all feedback for a conversation."""
        conversation_id = "conv_123"
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("fb_1", 5, "Great!", datetime.now()),
            ("fb_2", 4, "Good", datetime.now() - timedelta(hours=1))
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            f"/api/feedback/conversation/{conversation_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["feedback"]) == 2
    
    def test_get_user_feedback_history(self, client, mock_db, auth_token):
        """Test fetching feedback history for authenticated user."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("conv_1", 5, "Excellent", datetime.now()),
            ("conv_2", 3, "Average", datetime.now() - timedelta(days=1))
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/feedback/my-feedback",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["feedback"]) == 2
    
    def test_get_recent_feedback(self, client, mock_db, auth_token):
        """Test fetching recent feedback across all conversations."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("conv_1", 5, "Great", datetime.now()),
            ("conv_2", 4, "Good", datetime.now() - timedelta(hours=2)),
            ("conv_3", 3, "OK", datetime.now() - timedelta(hours=5))
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/feedback/recent?limit=10",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["feedback"]) == 3


# ================================
# Test Aggregate Statistics
# ================================

class TestAggregateStatistics:
    """Test suite for aggregate feedback statistics."""
    
    def test_get_overall_satisfaction_rate(self, client, mock_db, auth_token):
        """Test calculating overall satisfaction rate."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (4.2, 1500)  # avg rating, total count
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/feedback/stats/satisfaction",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["average_rating"] == 4.2
        assert data["total_ratings"] == 1500
    
    def test_get_feedback_trends(self, client, mock_db, auth_token):
        """Test fetching feedback trends over time."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("2025-01-01", 4.1, 50),
            ("2025-01-02", 4.3, 60),
            ("2025-01-03", 4.5, 55)
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/feedback/stats/trends?days=7",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["daily_stats"]) == 3
    
    def test_get_common_feedback_tags(self, client, mock_db, auth_token):
        """Test fetching most common feedback tags."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("accurate", 250),
            ("fast", 200),
            ("helpful", 180),
            ("detailed", 150)
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/feedback/stats/tags?limit=10",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["tags"]) == 4
        assert data["tags"][0]["tag"] == "accurate"
        assert data["tags"][0]["count"] == 250
    
    def test_get_rating_distribution(self, client, mock_db, auth_token):
        """Test fetching distribution of ratings."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (5, 800),
            (4, 500),
            (3, 150),
            (2, 40),
            (1, 10)
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/feedback/stats/distribution",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["distribution"]) == 5
        assert data["distribution"][0]["rating"] == 5
        assert data["distribution"][0]["count"] == 800


# ================================
# Test Feedback Moderation
# ================================

class TestFeedbackModeration:
    """Test suite for feedback moderation features."""
    
    def test_flag_inappropriate_feedback(self, client, mock_db, auth_token):
        """Test flagging feedback as inappropriate."""
        flag_data = {
            "feedback_id": "fb_123",
            "reason": "spam"
        }
        
        response = client.post(
            "/api/feedback/flag",
            json=flag_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        mock_db.commit.assert_called_once()
    
    def test_delete_feedback(self, client, mock_db, auth_token):
        """Test deleting own feedback."""
        feedback_id = "fb_123"
        
        response = client.delete(
            f"/api/feedback/{feedback_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 204
        mock_db.commit.assert_called_once()
    
    def test_update_feedback(self, client, mock_db, auth_token):
        """Test updating existing feedback."""
        feedback_id = "fb_123"
        update_data = {
            "rating": 4,
            "feedback_text": "Updated: Still good but not perfect"
        }
        
        response = client.patch(
            f"/api/feedback/{feedback_id}",
            json=update_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        mock_db.commit.assert_called_once()


# ================================
# Test Error Handling
# ================================

class TestFeedbackErrorHandling:
    """Test suite for error handling in feedback endpoints."""
    
    def test_submit_feedback_database_error(self, client, mock_db, auth_token, sample_feedback):
        """Test handling database error during feedback submission."""
        mock_db.commit.side_effect = Exception("Database connection lost")
        
        response = client.post(
            "/api/feedback",
            json=sample_feedback,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 500
        mock_db.rollback.assert_called_once()
    
    def test_get_nonexistent_conversation_feedback(self, client, mock_db, auth_token):
        """Test fetching feedback for non-existent conversation."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/feedback/conversation/nonexistent_conv",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["feedback"]) == 0
    
    def test_rate_nonexistent_message(self, client, mock_db, auth_token):
        """Test rating a message that doesn't exist."""
        rating_data = {
            "message_id": "nonexistent_msg",
            "rating_type": "thumbs_up"
        }
        
        mock_db.execute.return_value.fetchone.return_value = None
        
        response = client.post(
            "/api/feedback/rate",
            json=rating_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 404
