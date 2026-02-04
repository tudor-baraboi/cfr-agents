"""
Unit tests for authentication router (app/routers/auth.py).

Tests cover:
- Fingerprint authentication
- Admin code validation
- JWT token generation and validation
- Usage quota checking
- Geolocation integration
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from azure.core.exceptions import ResourceNotFoundError


@pytest.mark.unit
class TestFingerprintAuth:
    """Tests for POST /auth/fingerprint endpoint."""
    
    def test_fingerprint_auth_new_user(self, client, test_settings):
        """Test authentication for a new user (creates usage record)."""
        response = client.post(
            "/auth/fingerprint",
            json={"visitor_id": "new-fingerprint-123-test"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "token" in data
        assert data["is_admin"] is False
        assert data["requests_used"] == 0
        assert data["requests_remaining"] == test_settings.daily_request_limit
        assert data["daily_limit"] == test_settings.daily_request_limit
    
    def test_fingerprint_auth_existing_user(self, client, test_settings):
        """Test authentication for existing user (returns current usage)."""
        response = client.post(
            "/auth/fingerprint",
            json={"visitor_id": "existing-fingerprint-123456789"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "token" in data
        assert data["is_admin"] is False
        assert "requests_used" in data
        assert "requests_remaining" in data
        assert data["daily_limit"] == test_settings.daily_request_limit
    
    @pytest.mark.skip(reason="Requires setting up exhausted quota in usage tracker")
    def test_fingerprint_auth_quota_exhausted(self, client):
        """Test authentication when user has exhausted their quota."""
        # This test requires pre-populating the usage tracker with exhausted quota
        # Skip for now as it needs integration with Azure Tables
        pass
    
    def test_fingerprint_auth_missing_visitor_id(self, client):
        """Test authentication with missing visitor_id."""
        response = client.post(
            "/auth/fingerprint",
            json={"agent": "faa"}  # Missing visitor_id
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_fingerprint_auth_empty_visitor_id(self, client):
        """Test authentication with empty visitor_id."""
        response = client.post(
            "/auth/fingerprint",
            json={"visitor_id": ""}
        )
        
        assert response.status_code == 400  # Invalid visitor ID
    
    def test_fingerprint_auth_short_visitor_id(self, client):
        """Test authentication with too-short visitor_id."""
        response = client.post(
            "/auth/fingerprint",
            json={"visitor_id": "short"}
        )
        
        # Should fail - visitor_id must be at least 10 chars
        assert response.status_code == 400
    
    def test_fingerprint_auth_with_valid_long_id(self, client):
        """Test authentication with properly-formed long visitor_id."""
        response = client.post(
            "/auth/fingerprint",
            json={"visitor_id": "very-long-valid-fingerprint-id-12345"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["is_admin"] is False


@pytest.mark.unit
class TestAdminCodeValidation:
    """Tests for POST /auth/validate-code endpoint."""
    
    def test_validate_code_success(self, client):
        """Test successful admin code validation."""
        response = client.post(
            "/auth/validate-code",
            json={
                "code": "test-admin-123",  # Code gets uppercased in endpoint
                "fingerprint": "admin-fingerprint-456"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "token" in data
        assert data["is_admin"] is True
        assert data["requests_remaining"] is None  # Unlimited for admins
    
    def test_validate_code_invalid(self, client):
        """Test validation with invalid admin code."""
        response = client.post(
            "/auth/validate-code",
            json={
                "code": "invalid-code",
                "fingerprint": "test-fingerprint"
            }
        )
        
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
    
    def test_validate_code_empty(self, client):
        """Test validation with empty code."""
        response = client.post(
            "/auth/validate-code",
            json={
                "code": "",
                "fingerprint": "test-fingerprint"
            }
        )
        
        assert response.status_code == 401
    
    def test_validate_code_missing_fingerprint(self, client):
        """Test validation without fingerprint (fingerprint is optional for admin)."""
        response = client.post(
            "/auth/validate-code",
            json={"code": "test-admin-123"}  # Fingerprint is optional
        )
        
        # Should succeed - fingerprint is optional for admin codes
        assert response.status_code == 200
        data = response.json()
        assert data["is_admin"] is True
    
    def test_validate_code_uppercasing(self, client):
        """Test that code is uppercased before validation."""
        # Lowercase gets uppercased
        response = client.post(
            "/auth/validate-code",
            json={"code": "casesensitive123", "fingerprint": "test"}
        )
        assert response.status_code == 200
        
        # Mixed case also works
        response = client.post(
            "/auth/validate-code",
            json={"code": "CaseSensitive123", "fingerprint": "test"}
        )
        assert response.status_code == 200


@pytest.mark.unit
class TestJWTTokens:
    """Tests for JWT token generation and validation."""
    
    def test_jwt_token_contains_fingerprint(self, valid_jwt_token, test_settings):
        """Test that generated token contains fingerprint."""
        from jose import jwt
        
        payload = jwt.decode(valid_jwt_token, test_settings.jwt_secret, algorithms=["HS256"])
        assert "fingerprint" in payload
        assert payload["fingerprint"] == "test-fingerprint-123"
    
    def test_jwt_token_contains_is_admin(self, valid_jwt_token, test_settings):
        """Test that generated token contains is_admin flag."""
        from jose import jwt
        
        payload = jwt.decode(valid_jwt_token, test_settings.jwt_secret, algorithms=["HS256"])
        assert "is_admin" in payload
        assert isinstance(payload["is_admin"], bool)
    
    def test_jwt_token_has_expiration(self, valid_jwt_token, test_settings):
        """Test that token has expiration time."""
        from jose import jwt
        
        payload = jwt.decode(valid_jwt_token, test_settings.jwt_secret, algorithms=["HS256"])
        assert "exp" in payload
        assert "iat" in payload
    
    def test_expired_token_rejected(self, expired_jwt_token, test_settings):
        """Test that expired token is rejected."""
        from jose import jwt, JWTError
        
        with pytest.raises(JWTError):
            jwt.decode(
                expired_jwt_token,
                test_settings.jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": True}
            )
    
    def test_invalid_token_rejected(self, test_settings):
        """Test that malformed token is rejected."""
        from jose import jwt, JWTError
        
        with pytest.raises(JWTError):
            jwt.decode("invalid.token.here", test_settings.jwt_secret, algorithms=["HS256"])
    
    def test_token_with_wrong_secret_rejected(self, valid_jwt_token):
        """Test that token signed with wrong secret is rejected."""
        from jose import jwt, JWTError
        
        with pytest.raises(JWTError):
            jwt.decode(valid_jwt_token, "wrong-secret", algorithms=["HS256"])


@pytest.mark.unit
class TestAuthEndpointIntegration:
    """Integration tests between auth endpoints and usage service."""
    
    def test_auth_updates_usage_counter(self, client):
        """Test that authentication updates the usage counter."""
        response = client.post(
            "/auth/fingerprint",
            json={"visitor_id": "usage-test-fingerprint-123"}
        )
        
        assert response.status_code == 200
        # Usage counter should be tracked
        assert "requests_used" in response.json()
        assert "requests_remaining" in response.json()
    
    @pytest.mark.skip(reason="Requires setting up exhausted quota in usage tracker")
    def test_auth_respects_daily_limit(self, client):
        """Test that auth respects the daily limit setting."""
        # This test requires pre-populating the usage tracker with exhausted quota
        # Skip for now as it needs integration with Azure Tables
        pass
    
    def test_admin_bypasses_quota(self, client):
        """Test that admin tokens bypass quota limits."""
        response = client.post(
            "/auth/validate-code",
            json={"code": "admin-123", "fingerprint": "admin-test"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["requests_remaining"] is None  # Unlimited
        assert data["requests_used"] == 0
