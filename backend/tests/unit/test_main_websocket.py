"""
WebSocket endpoint tests for main.py

Tests the /ws/chat/{conversation_id} WebSocket endpoint including:
- Connection lifecycle and auth validation
- Message handling
- Error handling
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.unit
class TestWebSocketConnection:
    """Tests for WebSocket connection lifecycle."""

    def test_websocket_rejects_no_token(self):
        """WebSocket without token query param is rejected (4001)."""
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/chat/conv-123") as ws:
                # Should get closed by server before we can do anything
                ws.receive_json()

    def test_websocket_rejects_invalid_token(self):
        """WebSocket with invalid token is rejected (4001)."""
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/chat/conv-123?token=bad-token") as ws:
                ws.receive_json()

    def test_websocket_rejects_expired_token(self, expired_jwt_token):
        """WebSocket with expired token is rejected."""
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect(
                f"/ws/chat/conv-123?token={expired_jwt_token}"
            ) as ws:
                ws.receive_json()

    def test_websocket_rejects_invalid_agent(self, valid_jwt_token):
        """WebSocket with unknown agent type is rejected."""
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect(
                f"/ws/chat/conv-123?token={valid_jwt_token}&agent=nonexistent"
            ) as ws:
                ws.receive_json()

    @patch("app.main.get_usage_tracker")
    def test_websocket_accepts_valid_token(self, mock_get_tracker, valid_jwt_token):
        """WebSocket with valid token connects and receives ping/messages."""
        mock_tracker = MagicMock()
        mock_tracker.check_quota = AsyncMock(return_value=(True, 1, 14))
        mock_tracker.close = AsyncMock()
        mock_get_tracker.return_value = mock_tracker

        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/chat/conv-123?token={valid_jwt_token}"
        ) as ws:
            # Server accepts and we're connected - just close
            pass

    @patch("app.main.get_usage_tracker")
    def test_websocket_quota_exceeded_non_admin(self, mock_get_tracker, valid_jwt_token):
        """Non-admin user whose quota is exceeded gets error and disconnect."""
        mock_tracker = MagicMock()
        mock_tracker.check_quota = AsyncMock(return_value=(False, 15, 0))
        mock_tracker.close = AsyncMock()
        mock_get_tracker.return_value = mock_tracker

        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/chat/conv-123?token={valid_jwt_token}"
        ) as ws:
            # Server should send error before closing
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "daily" in data["content"].lower() or "quota" in data["content"].lower() or "queries" in data["content"].lower()

    @patch("app.main.get_usage_tracker")
    def test_websocket_admin_bypasses_quota(self, mock_get_tracker, admin_jwt_token):
        """Admin user connects without quota check."""
        mock_tracker = MagicMock()
        mock_tracker.close = AsyncMock()
        mock_get_tracker.return_value = mock_tracker

        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/chat/conv-123?token={admin_jwt_token}"
        ) as ws:
            # Admin connects fine - just close
            pass
        # check_quota should not be called for admin
        mock_tracker.check_quota.assert_not_called()


@pytest.mark.unit
class TestWebSocketMessageHandling:
    """Tests for message handling in the WebSocket."""

    @patch("app.main.handle_conversation")
    @patch("app.main.get_usage_tracker")
    def test_empty_message_returns_error(self, mock_get_tracker, mock_handle, valid_jwt_token):
        """Sending empty message returns error response."""
        mock_tracker = MagicMock()
        mock_tracker.check_quota = AsyncMock(return_value=(True, 0, 15))
        mock_tracker.close = AsyncMock()
        mock_get_tracker.return_value = mock_tracker

        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/chat/conv-123?token={valid_jwt_token}"
        ) as ws:
            ws.send_json({"message": ""})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "Empty message" in resp["content"]

    @patch("app.main.handle_conversation")
    @patch("app.main.get_usage_tracker")
    def test_valid_message_streams_response(self, mock_get_tracker, mock_handle, valid_jwt_token):
        """Valid message triggers streaming response from orchestrator."""
        mock_tracker = MagicMock()
        mock_tracker.check_quota = AsyncMock(return_value=(True, 0, 15))
        mock_tracker.increment_usage = AsyncMock(return_value=1)
        mock_tracker.close = AsyncMock()
        mock_get_tracker.return_value = mock_tracker

        # Mock handle_conversation as async generator
        async def mock_stream(*args, **kwargs):
            yield {"type": "text", "content": "HIRF stands for "}
            yield {"type": "text", "content": "High-Intensity Radiated Fields"}

        mock_handle.return_value = mock_stream()

        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/chat/conv-123?token={valid_jwt_token}"
        ) as ws:
            ws.send_json({"message": "What is HIRF?"})

            # Receive streamed chunks
            chunks = []
            while True:
                resp = ws.receive_json()
                if resp["type"] == "done":
                    break
                if resp["type"] == "ping":
                    continue
                if resp["type"] == "quota_update":
                    continue
                chunks.append(resp)

            assert len(chunks) == 2
            assert chunks[0]["content"] == "HIRF stands for "


@pytest.mark.unit
class TestWebSocketErrorHandling:
    """Tests for error handling in the WebSocket."""

    @patch("app.main.handle_conversation")
    @patch("app.main.get_usage_tracker")
    def test_orchestrator_error_sends_error_message(self, mock_get_tracker, mock_handle, valid_jwt_token):
        """Orchestrator exception results in error message to client."""
        mock_tracker = MagicMock()
        mock_tracker.check_quota = AsyncMock(return_value=(True, 0, 15))
        mock_tracker.close = AsyncMock()
        mock_get_tracker.return_value = mock_tracker

        # Mock handle_conversation raising an exception
        async def mock_error_stream(*args, **kwargs):
            raise RuntimeError("Claude API timeout")
            yield  # make it a generator

        mock_handle.return_value = mock_error_stream()

        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/chat/conv-123?token={valid_jwt_token}"
        ) as ws:
            ws.send_json({"message": "Question"})

            # Receive error
            resp = ws.receive_json()
            while resp.get("type") == "ping":
                resp = ws.receive_json()
            assert resp["type"] == "error"
