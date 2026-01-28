"""
In-memory conversation state.

TODO: Replace with PostgreSQL for persistence.
"""

from typing import Any

# In-memory store: conversation_id -> list of messages
_conversations: dict[str, list[dict[str, Any]]] = {}


def get_history(conversation_id: str) -> list[dict[str, Any]]:
    """Get conversation history for a conversation ID."""
    if conversation_id not in _conversations:
        _conversations[conversation_id] = []
    return _conversations[conversation_id]


def add_message(conversation_id: str, message: dict[str, Any]) -> None:
    """Add a message to conversation history."""
    if conversation_id not in _conversations:
        _conversations[conversation_id] = []
    _conversations[conversation_id].append(message)


def clear_history(conversation_id: str) -> None:
    """Clear conversation history."""
    _conversations[conversation_id] = []
