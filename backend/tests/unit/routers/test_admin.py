"""
Unit tests for admin dashboard router endpoints.

Tests the admin.py router which provides endpoints for:
- Usage analytics and statistics
- Trial token management
- Quota configuration
- User activity monitoring
- System health metrics
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.routers import admin


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
def admin_token():
    """Mock admin JWT token."""
    return "admin_jwt_token_here"


# ================================
# Test Usage Analytics Endpoints
# ================================

class TestUsageAnalytics:
    """Test suite for usage analytics endpoints."""
    
    def test_get_global_usage_stats(self, client, mock_db, admin_token):
        """Test fetching global usage statistics."""
        # Mock database query result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (datetime.now() - timedelta(days=1), 1000, 50),
            (datetime.now(), 2000, 75)
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/admin/usage/global",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "total_tokens" in data
        assert "total_conversations" in data
        assert "daily_breakdown" in data
    
    def test_get_usage_by_user(self, client, mock_db, admin_token):
        """Test fetching usage statistics by user."""
        user_fingerprint = "test_fingerprint_123"
        
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (5000, 25, 10)
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            f"/api/admin/usage/user/{user_fingerprint}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["fingerprint"] == user_fingerprint
        assert "total_tokens" in data
        assert "conversation_count" in data
    
    def test_get_usage_by_date_range(self, client, mock_db, admin_token):
        """Test fetching usage statistics for date range."""
        start_date = "2025-01-01"
        end_date = "2025-01-31"
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("2025-01-15", 5000, 100),
            ("2025-01-20", 7500, 150)
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            f"/api/admin/usage/date-range?start={start_date}&end={end_date}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["daily_usage"]) == 2
        assert "total_tokens" in data
    
    def test_get_top_users(self, client, mock_db, admin_token):
        """Test fetching top users by token usage."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("user_1", 10000, 50),
            ("user_2", 8000, 40),
            ("user_3", 6000, 30)
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/admin/usage/top-users?limit=10",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 3
        assert data["users"][0]["total_tokens"] == 10000


# ================================
# Test Trial Token Management
# ================================

class TestTrialTokenManagement:
    """Test suite for trial token management."""
    
    def test_create_trial_code(self, client, mock_db, admin_token):
        """Test creating a new trial code."""
        trial_data = {
            "code": "TRIAL2025",
            "max_tokens": 100000,
            "max_users": 50,
            "expiry_date": "2025-12-31"
        }
        
        response = client.post(
            "/api/admin/trials",
            json=trial_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["code"] == "TRIAL2025"
        assert data["max_tokens"] == 100000
        mock_db.commit.assert_called_once()
    
    def test_get_trial_code_usage(self, client, mock_db, admin_token):
        """Test fetching trial code usage statistics."""
        trial_code = "TRIAL2025"
        
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (
            "TRIAL2025", 50000, 25, 100000, 50
        )
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            f"/api/admin/trials/{trial_code}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == trial_code
        assert data["tokens_used"] == 50000
        assert data["users_count"] == 25
    
    def test_update_trial_code(self, client, mock_db, admin_token):
        """Test updating trial code limits."""
        trial_code = "TRIAL2025"
        update_data = {
            "max_tokens": 150000,
            "max_users": 100
        }
        
        response = client.patch(
            f"/api/admin/trials/{trial_code}",
            json=update_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        mock_db.commit.assert_called_once()
    
    def test_deactivate_trial_code(self, client, mock_db, admin_token):
        """Test deactivating a trial code."""
        trial_code = "TRIAL2025"
        
        response = client.delete(
            f"/api/admin/trials/{trial_code}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 204
        mock_db.commit.assert_called_once()
    
    def test_list_all_trial_codes(self, client, mock_db, admin_token):
        """Test listing all trial codes."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("TRIAL2025", 50000, 25, True),
            ("BETA2025", 75000, 40, True),
            ("EXPIRED2024", 100000, 50, False)
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/admin/trials",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["trials"]) == 3


# ================================
# Test Quota Configuration
# ================================

class TestQuotaConfiguration:
    """Test suite for quota configuration endpoints."""
    
    def test_get_global_quota_config(self, client, mock_db, admin_token):
        """Test fetching global quota configuration."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (50000, 10)
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/admin/quota/config",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["daily_token_limit"] == 50000
        assert data["rate_limit_per_minute"] == 10
    
    def test_update_global_quota(self, client, mock_db, admin_token):
        """Test updating global quota limits."""
        quota_update = {
            "daily_token_limit": 75000,
            "rate_limit_per_minute": 15
        }
        
        response = client.put(
            "/api/admin/quota/config",
            json=quota_update,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        mock_db.commit.assert_called_once()
    
    def test_set_user_custom_quota(self, client, mock_db, admin_token):
        """Test setting custom quota for specific user."""
        user_fingerprint = "premium_user_123"
        quota_data = {
            "daily_token_limit": 100000,
            "rate_limit_per_minute": 20
        }
        
        response = client.put(
            f"/api/admin/quota/user/{user_fingerprint}",
            json=quota_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        mock_db.commit.assert_called_once()
    
    def test_remove_user_custom_quota(self, client, mock_db, admin_token):
        """Test removing custom quota for user."""
        user_fingerprint = "premium_user_123"
        
        response = client.delete(
            f"/api/admin/quota/user/{user_fingerprint}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 204
        mock_db.commit.assert_called_once()
    
    def test_get_users_with_custom_quotas(self, client, mock_db, admin_token):
        """Test listing users with custom quota settings."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("user_1", 100000, 20),
            ("user_2", 150000, 25)
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/admin/quota/custom-users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 2


# ================================
# Test User Activity Monitoring
# ================================

class TestUserActivityMonitoring:
    """Test suite for user activity monitoring."""
    
    def test_get_active_users_count(self, client, mock_db, admin_token):
        """Test fetching count of active users."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (125,)
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/admin/users/active-count?days=7",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["active_users"] == 125
        assert data["period_days"] == 7
    
    def test_get_user_conversation_history(self, client, mock_db, admin_token):
        """Test fetching conversation history for a user."""
        user_fingerprint = "test_user_123"
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("conv_1", datetime.now(), 5000, 10),
            ("conv_2", datetime.now() - timedelta(hours=2), 3000, 8)
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            f"/api/admin/users/{user_fingerprint}/conversations",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["conversations"]) == 2
    
    def test_get_user_last_activity(self, client, mock_db, admin_token):
        """Test fetching user's last activity timestamp."""
        user_fingerprint = "test_user_123"
        
        mock_result = MagicMock()
        last_seen = datetime.now() - timedelta(hours=1)
        mock_result.fetchone.return_value = (last_seen,)
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            f"/api/admin/users/{user_fingerprint}/last-activity",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "last_activity" in data
    
    def test_search_users(self, client, mock_db, admin_token):
        """Test searching users by criteria."""
        search_params = {
            "min_tokens": 5000,
            "max_days_inactive": 30
        }
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("user_1", 10000, datetime.now()),
            ("user_2", 7500, datetime.now() - timedelta(days=5))
        ]
        mock_db.execute.return_value = mock_result
        
        response = client.get(
            "/api/admin/users/search",
            params=search_params,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 2


# ================================
# Test System Health Monitoring
# ================================

class TestSystemHealthMonitoring:
    """Test suite for system health metrics."""
    
    @patch('app.routers.admin.get_database_status')
    def test_get_database_health(self, mock_db_status, client, admin_token):
        """Test checking database connection health."""
        mock_db_status.return_value = {
            "status": "healthy",
            "response_time_ms": 15,
            "connection_pool": {"active": 5, "idle": 10}
        }
        
        response = client.get(
            "/api/admin/health/database",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["response_time_ms"] < 100
    
    @patch('app.routers.admin.get_azure_search_status')
    def test_get_search_index_health(self, mock_search_status, client, admin_token):
        """Test checking Azure Search index health."""
        mock_search_status.return_value = {
            "status": "healthy",
            "index_count": 3,
            "document_counts": {
                "faa-index": 5000,
                "nrc-index": 3000,
                "dod-index": 2000
            }
        }
        
        response = client.get(
            "/api/admin/health/search",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["index_count"] == 3
    
    @patch('app.routers.admin.get_claude_api_status')
    def test_get_claude_api_health(self, mock_claude_status, client, admin_token):
        """Test checking Claude API connectivity."""
        mock_claude_status.return_value = {
            "status": "healthy",
            "latency_ms": 250,
            "rate_limit_remaining": 950
        }
        
        response = client.get(
            "/api/admin/health/claude",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    @patch('app.routers.admin.get_cache_status')
    def test_get_cache_health(self, mock_cache_status, client, admin_token):
        """Test checking cache system health."""
        mock_cache_status.return_value = {
            "status": "healthy",
            "hit_rate": 0.85,
            "size_mb": 250,
            "evictions_last_hour": 15
        }
        
        response = client.get(
            "/api/admin/health/cache",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["hit_rate"] > 0.8
    
    def test_get_overall_system_health(self, client, admin_token):
        """Test fetching overall system health summary."""
        with patch.multiple(
            'app.routers.admin',
            get_database_status=MagicMock(return_value={"status": "healthy"}),
            get_azure_search_status=MagicMock(return_value={"status": "healthy"}),
            get_claude_api_status=MagicMock(return_value={"status": "healthy"}),
            get_cache_status=MagicMock(return_value={"status": "healthy"})
        ):
            response = client.get(
                "/api/admin/health",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["overall_status"] == "healthy"
            assert "components" in data


# ================================
# Test Authorization & Security
# ================================

class TestAdminAuthorization:
    """Test suite for admin authorization checks."""
    
    def test_unauthorized_access_no_token(self, client):
        """Test accessing admin endpoint without token."""
        response = client.get("/api/admin/usage/global")
        assert response.status_code == 401
    
    def test_unauthorized_access_invalid_token(self, client):
        """Test accessing admin endpoint with invalid token."""
        response = client.get(
            "/api/admin/usage/global",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401
    
    def test_forbidden_access_non_admin_token(self, client):
        """Test accessing admin endpoint with non-admin token."""
        user_token = "regular_user_token"
        response = client.get(
            "/api/admin/usage/global",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        # Should be forbidden since user is not admin
        assert response.status_code in [401, 403]
    
    @patch('app.routers.admin.verify_admin_token')
    def test_successful_admin_authentication(self, mock_verify, client, admin_token):
        """Test successful admin authentication."""
        mock_verify.return_value = {"user_id": "admin_123", "role": "admin"}
        
        response = client.get(
            "/api/admin/health",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        mock_verify.assert_called_once()
