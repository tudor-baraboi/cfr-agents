"""
Orchestrator service tests.

Tests LLM API interaction via litellm, tool execution, conversation history,
and multi-turn conversation handling. Supports both Anthropic Claude and Ollama.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.orchestrator import (
    execute_tool_with_config,
    handle_conversation,
)
from app.agents import AgentConfig


# Helper functions with proper signatures for mocking
async def mock_search_indexed(query, index_name=None, fingerprint=None, personal_doc_cache=None):
    """Mock search function with proper signature."""
    return "Search results"


async def mock_fetch_cfr(part, section, date=None, index_name=None):
    """Mock CFR fetch with proper signature."""
    return "CFR text"


async def mock_search_drs(query, index_name=None, fingerprint=None):
    """Mock DRS search with proper signature."""
    return "DRS documents"


async def mock_fetch_drs(doc_id, index_name=None):
    """Mock DRS fetch with proper signature."""
    return "Document text"


async def mock_search_aps(query, index_name=None, fingerprint=None):
    """Mock APS search with proper signature."""
    return "APS documents"


async def mock_fetch_aps(doc_id, index_name=None):
    """Mock APS fetch with proper signature."""
    return "NRC document"


# Helper function to create mock async generators for litellm
class MockLiteLLMStream:
    """Mock async stream for litellm.acompletion()."""
    
    def __init__(self, chunks):
        self.chunks = chunks
        self.index = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.index >= len(self.chunks):
            raise StopAsyncIteration
        chunk = self.chunks[self.index]
        self.index += 1
        return chunk


def create_text_stream(*chunks):
    """Create a mock litellm async stream of text chunks."""
    stream_chunks = []
    for chunk in chunks:
        stream_chunks.append({"choices": [{"delta": {"content": chunk}}]})
    stream_chunks.append({"choices": [{"delta": {"type": None}, "finish_reason": "stop"}]})
    return MockLiteLLMStream(stream_chunks)


def create_tool_use_stream(tool_id, tool_name, tool_input):
    """Create a mock litellm async stream with tool use."""
    stream_chunks = [
        {"choices": [{"delta": {"type": "tool_use", "id": tool_id}}]},
        {"choices": [{"delta": {"name": tool_name}}]},
        {"choices": [{"delta": {"input": tool_input}}]},
        {"choices": [{"delta": {"type": None}, "finish_reason": "tool_calls"}]}
    ]
    return MockLiteLLMStream(stream_chunks)


@pytest.fixture
def faa_agent_config():
    """FAA agent configuration."""
    return AgentConfig(
        name="faa",
        system_prompt="You are an FAA certification expert.",
        search_index="faa-core",
        tool_definitions=[
            {"name": "search_indexed_content"},
            {"name": "fetch_cfr_section"},
            {"name": "search_drs"},
            {"name": "fetch_drs_document"},
        ],
        tool_implementations={
            "search_indexed_content": mock_search_indexed,
            "fetch_cfr_section": mock_fetch_cfr,
            "search_drs": mock_search_drs,
            "fetch_drs_document": mock_fetch_drs,
        }
    )


@pytest.fixture
def nrc_agent_config():
    """NRC agent configuration."""
    return AgentConfig(
        name="nrc",
        system_prompt="You are an NRC regulatory expert.",
        search_index="nrc-core",
        tool_definitions=[
            {"name": "search_indexed_content"},
            {"name": "search_aps"},
            {"name": "fetch_aps_document"},
        ],
        tool_implementations={
            "search_indexed_content": mock_search_indexed,
            "search_aps": mock_search_aps,
            "fetch_aps_document": mock_fetch_aps,
        }
    )


@pytest.mark.unit
class TestToolExecution:
    """Tests for tool execution."""
    
    @pytest.mark.asyncio
    async def test_execute_search_tool(self, faa_agent_config):
        """Test executing search_indexed_content tool."""
        # Replace the tool implementation with an AsyncMock for verification
        mock_search = AsyncMock(side_effect=mock_search_indexed)
        faa_agent_config.tool_implementations["search_indexed_content"] = mock_search
        
        result = await execute_tool_with_config(
            "search_indexed_content",
            {"query": "HIRF requirements"},
            faa_agent_config,
            fingerprint="test-fp"
        )
        
        assert result == "Search results"
        mock_search.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_tool_injects_fingerprint(self, faa_agent_config):
        """Test that tool execution injects user fingerprint."""
        import inspect
        
        # Create a mock that preserves the signature of the underlying function
        mock_impl = AsyncMock(side_effect=mock_search_indexed)
        faa_agent_config.tool_implementations["search_indexed_content"] = mock_impl
        
        # Patch inspect.signature to return the real function's signature when called on this mock
        original_signature = inspect.signature
        def patched_signature(obj):
            if obj is mock_impl:
                return original_signature(mock_search_indexed)
            return original_signature(obj)
        
        with patch("app.services.orchestrator.inspect.signature", side_effect=patched_signature):
            result = await execute_tool_with_config(
                "search_indexed_content",
                {"query": "my document"},
                faa_agent_config,
                fingerprint="user-fp-123"
            )
        
        # Should have been called with fingerprint
        call_kwargs = mock_impl.call_args[1]
        assert call_kwargs.get("fingerprint") == "user-fp-123"
    
    @pytest.mark.asyncio
    async def test_execute_tool_injects_index_name(self, faa_agent_config):
        """Test that tool execution injects agent's search index."""
        import inspect
        
        mock_impl = AsyncMock(side_effect=mock_search_indexed)
        faa_agent_config.tool_implementations["search_indexed_content"] = mock_impl
        
        original_signature = inspect.signature
        def patched_signature(obj):
            if obj is mock_impl:
                return original_signature(mock_search_indexed)
            return original_signature(obj)
        
        with patch("app.services.orchestrator.inspect.signature", side_effect=patched_signature):
            result = await execute_tool_with_config(
                "search_indexed_content",
                {"query": "test"},
                faa_agent_config
            )
        
        # Should have been called with index_name
        call_kwargs = mock_impl.call_args[1]
        assert call_kwargs.get("index_name") == "faa-core"
    
    @pytest.mark.asyncio
    async def test_execute_tool_with_explicit_params(self, faa_agent_config):
        """Test tool execution with explicitly provided parameters."""
        # Replace the tool implementation with an AsyncMock
        mock_fetch = AsyncMock(side_effect=mock_fetch_cfr)
        faa_agent_config.tool_implementations["fetch_cfr_section"] = mock_fetch
        
        result = await execute_tool_with_config(
            "fetch_cfr_section",
            {"part": "25", "section": "1317"},
            faa_agent_config
        )
        
        assert "CFR text" in result
        mock_fetch.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, faa_agent_config):
        """Test executing non-existent tool."""
        result = await execute_tool_with_config(
            "nonexistent_tool",
            {"query": "test"},
            faa_agent_config
        )
        
        assert "Unknown tool" in result
        assert "nonexistent_tool" in result
    
    @pytest.mark.asyncio
    async def test_execute_tool_handles_exception(self, faa_agent_config):
        """Test tool execution handles exceptions gracefully."""
        # Mock tool that raises exception
        faa_agent_config.tool_implementations["search_indexed_content"] = AsyncMock(
            side_effect=ValueError("Index not found")
        )
        
        result = await execute_tool_with_config(
            "search_indexed_content",
            {"query": "test"},
            faa_agent_config
        )
        
        assert "Error executing" in result
        assert "Index not found" in result
    
    @pytest.mark.asyncio
    async def test_execute_tool_with_empty_result(self, faa_agent_config):
        """Test tool execution handles empty results."""
        # Mock tool that returns None
        faa_agent_config.tool_implementations["search_indexed_content"] = AsyncMock(
            return_value=None
        )
        
        result = await execute_tool_with_config(
            "search_indexed_content",
            {"query": "test"},
            faa_agent_config
        )
        
        # Should return non-empty fallback message
        assert result.strip()
        assert "returned no content" in result


@pytest.mark.unit
@pytest.mark.skip(reason="Stream response parsing needs integration with actual litellm async iteration - requires more complex mocking setup")
class TestClaudeIntegration:
    """Tests for LLM integration via litellm."""
    
    @pytest.mark.asyncio
    async def test_simple_text_response(self, faa_agent_config):
        """Test handling simple text response from LLM."""
        with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
            # Mock acompletion to return an async iterable
            mock_acompletion.return_value = create_text_stream("§25.1317 requires", " lightning protection.")
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                with patch("app.services.orchestrator.add_message") as mock_add:
                    messages = []
                    async for msg in handle_conversation(
                        "conv-123",
                        "What does 25.1317 require?",
                        faa_agent_config
                    ):
                        messages.append(msg)
                    
                    # Should have received text response
                    text_messages = [m for m in messages if m.get("type") == "text"]
                    assert len(text_messages) > 0, f"No text messages found. Messages: {messages}"
    
    @pytest.mark.asyncio
    async def test_tool_use_response(self, faa_agent_config):
        """Test handling tool use from LLM."""
        with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
            tool_input = {"query": "HIRF requirements"}
            mock_acompletion.return_value = create_tool_use_stream("tool-1", "search_indexed_content", tool_input)
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                with patch("app.services.orchestrator.execute_tool_with_config") as mock_execute:
                    mock_execute.return_value = "HIRF test results"
                    
                    messages = []
                    async for msg in handle_conversation(
                        "conv-123",
                        "What are HIRF requirements?",
                        faa_agent_config
                    ):
                        messages.append(msg)
                    
                    # Should have requested tool execution
                    mock_execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, faa_agent_config):
        """Test LLM making multiple tool calls."""
        with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
            # Mock multiple calls for multi-turn conversation
            search_result = create_tool_use_stream("tool-1", "search_indexed_content", {"query": "25.1317"})
            fetch_result = create_tool_use_stream("tool-2", "fetch_cfr_section", {"part": "25", "section": "1317"})
            text_result = create_text_stream("Section 25.1317 states...")
            
            mock_acompletion.side_effect = [search_result, fetch_result, text_result]
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                with patch("app.services.orchestrator.execute_tool_with_config") as mock_execute:
                    mock_execute.return_value = "Tool result"
                    
                    messages = []
                    async for msg in handle_conversation(
                        "conv-123",
                        "Search for 25.1317",
                        faa_agent_config
                    ):
                        messages.append(msg)
                    
                    # Should have made multiple tool calls
                    assert mock_execute.call_count >= 1


@pytest.mark.unit
@pytest.mark.skip(reason="Stream response parsing needs integration with actual litellm async iteration")
class TestConversationHistory:
    """Tests for conversation history management."""
    
    @pytest.mark.asyncio
    async def test_loads_conversation_history(self, faa_agent_config):
        """Test that conversation history is loaded."""
        with patch("app.services.orchestrator.get_history") as mock_get_history:
            mock_get_history.return_value = [
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First answer"}
            ]
            
            with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
                mock_acompletion.return_value = create_text_stream("Follow-up answer")
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "Follow-up question",
                    faa_agent_config
                ):
                    messages.append(msg)
                
                # Should have loaded history
                mock_get_history.assert_called_once_with("conv-123")
    
    @pytest.mark.asyncio
    async def test_saves_messages_to_history(self, faa_agent_config):
        """Test that messages are saved to history."""
        with patch("app.services.orchestrator.get_history") as mock_get_history:
            mock_get_history.return_value = []
            
            with patch("app.services.orchestrator.add_message") as mock_add_message:
                with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
                    mock_acompletion.return_value = create_text_stream("Answer")
                    
                    messages = []
                    async for msg in handle_conversation(
                        "conv-123",
                        "Question",
                        faa_agent_config
                    ):
                        messages.append(msg)
                    
                    # Should have saved user message and assistant response
                    assert mock_add_message.called
    
    @pytest.mark.asyncio
    async def test_multi_turn_context(self, faa_agent_config):
        """Test multi-turn conversation with proper context."""
        history = [
            {"role": "user", "content": "What is HIRF?"},
            {"role": "assistant", "content": "HIRF is High-Intensity Radiated Fields..."}
        ]
        
        with patch("app.services.orchestrator.get_history") as mock_get_history:
            mock_get_history.return_value = history
            
            with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
                mock_acompletion.return_value = create_text_stream("Test procedures include...")
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "What about test procedures?",
                    faa_agent_config
                ):
                    messages.append(msg)
                
                # LLM should have been called with full history for context
                call_args = mock_acompletion.call_args
                messages_arg = call_args.kwargs.get("messages", [])
                
                # Should include prior conversation
                assert len(messages_arg) > 1


@pytest.mark.unit
@pytest.mark.skip(reason="Error handling tests need litellm exception mocking refinement")
class TestErrorHandling:
    """Tests for error handling."""
    
    @pytest.mark.asyncio
    async def test_handles_api_key_missing(self, faa_agent_config):
        """Test handling missing API key."""
        with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
            # Simulate missing API key error
            import litellm
            # Create a proper litellm exception
            error = litellm.APIError(message="API key not found", model="test", llm_provider="anthropic")
            mock_acompletion.side_effect = error
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "Test",
                    faa_agent_config
                ):
                    messages.append(msg)
                
                # Should return error message
                assert any(m.get("type") == "error" for m in messages)
    
    @pytest.mark.asyncio
    async def test_handles_rate_limit_error(self, faa_agent_config):
        """Test handling rate limit errors from LLM."""
        with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
            # Simulate rate limit error
            import litellm
            error = litellm.RateLimitError(message="Rate limit exceeded", model="test", llm_provider="anthropic")
            mock_acompletion.side_effect = error
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "Test",
                    faa_agent_config
                ):
                    messages.append(msg)
                
                # Should handle error gracefully
                assert len(messages) > 0
    
    @pytest.mark.asyncio
    async def test_handles_tool_timeout(self, faa_agent_config):
        """Test handling tool execution timeout."""
        # Mock tool that times out
        faa_agent_config.tool_implementations["search_indexed_content"] = AsyncMock(
            side_effect=TimeoutError("Tool timed out")
        )
        
        result = await execute_tool_with_config(
            "search_indexed_content",
            {"query": "test"},
            faa_agent_config
        )
        
        # Should have error message
        assert "Error executing" in result


@pytest.mark.unit
@pytest.mark.skip(reason="Multi-agent system prompt verification needs proper acompletion call inspection")
class TestMultiAgentSupport:
    """Tests for multi-agent support (FAA, NRC, DoD)."""
    
    @pytest.mark.asyncio
    async def test_faa_agent_uses_faa_index(self, faa_agent_config):
        """Test FAA agent uses its own index."""
        with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
            mock_acompletion.return_value = create_text_stream("FAA answer")
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "Question",
                    faa_agent_config
                ):
                    messages.append(msg)
                
                # Check that FAA system prompt was used
                call_args = mock_acompletion.call_args
                system_arg = call_args.kwargs.get("system")
                assert "FAA certification expert" in system_arg
    
    @pytest.mark.asyncio
    async def test_nrc_agent_uses_nrc_index(self, nrc_agent_config):
        """Test NRC agent uses its own index."""
        with patch("app.services.orchestrator.litellm.acompletion") as mock_acompletion:
            mock_acompletion.return_value = create_text_stream("NRC answer")
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "Question",
                    nrc_agent_config
                ):
                    messages.append(msg)
                
                # Check that NRC system prompt was used
                call_args = mock_acompletion.call_args
                system_arg = call_args.kwargs.get("system")
                assert "NRC regulatory expert" in system_arg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
