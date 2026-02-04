"""
Orchestrator service tests.

Tests Claude API interaction, tool execution, conversation history,
and multi-turn conversation handling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from anthropic.types.message import Message
from anthropic.types.content_block import TextBlock, ToolUseBlock

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
        result = await execute_tool_with_config(
            "search_indexed_content",
            {"query": "HIRF requirements"},
            faa_agent_config,
            fingerprint="test-fp"
        )
        
        assert result == "Search results"
        faa_agent_config.tool_implementations["search_indexed_content"].assert_called_once()
    
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
        result = await execute_tool_with_config(
            "fetch_cfr_section",
            {"section": "25.1317"},
            faa_agent_config
        )
        
        assert "CFR text" in result
        faa_agent_config.tool_implementations["fetch_cfr_section"].assert_called_once()
    
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
class TestClaudeIntegration:
    """Tests for Claude API integration."""
    
    @pytest.mark.asyncio
    async def test_simple_text_response(self, faa_agent_config):
        """Test handling simple text response from Claude."""
        with patch("app.services.orchestrator.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [
                TextBlock(type="text", text="§25.1317 requires lightning protection.")
            ]
            mock_response.stop_reason = "end_turn"
            
            mock_client.return_value.messages.create = MagicMock(return_value=mock_response)
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "What does 25.1317 require?",
                    faa_agent_config
                ):
                    messages.append(msg)
                
                # Should have received text response
                assert any(m.get("type") == "text" for m in messages)
    
    @pytest.mark.asyncio
    async def test_tool_use_response(self, faa_agent_config):
        """Test handling tool use from Claude."""
        with patch("app.services.orchestrator.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [
                ToolUseBlock(
                    type="tool_use",
                    id="tool-1",
                    name="search_indexed_content",
                    input={"query": "HIRF requirements"}
                )
            ]
            mock_response.stop_reason = "tool_use"
            
            mock_client.return_value.messages.create = MagicMock(return_value=mock_response)
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "What are HIRF requirements?",
                    faa_agent_config
                ):
                    messages.append(msg)
                
                # Should have tool use message
                assert any(m.get("type") == "tool_use" for m in messages)
    
    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, faa_agent_config):
        """Test Claude making multiple tool calls."""
        with patch("app.services.orchestrator.anthropic.Anthropic") as mock_client:
            # First call returns tool use
            response1 = MagicMock()
            response1.content = [
                ToolUseBlock(
                    type="tool_use",
                    id="tool-1",
                    name="search_indexed_content",
                    input={"query": "25.1317"}
                )
            ]
            response1.stop_reason = "tool_use"
            
            # Second call returns different tool use
            response2 = MagicMock()
            response2.content = [
                ToolUseBlock(
                    type="tool_use",
                    id="tool-2",
                    name="fetch_cfr_section",
                    input={"section": "25.1317"}
                )
            ]
            response2.stop_reason = "tool_use"
            
            # Final call returns text
            response3 = MagicMock()
            response3.content = [
                TextBlock(type="text", text="Section 25.1317 states...")
            ]
            response3.stop_reason = "end_turn"
            
            mock_client.return_value.messages.create = MagicMock(
                side_effect=[response1, response2, response3]
            )
            
            with patch("app.services.orchestrator.get_history") as mock_get_history:
                mock_get_history.return_value = []
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "Explain 25.1317",
                    faa_agent_config
                ):
                    messages.append(msg)
                
                # Should have tool uses and final response
                tool_messages = [m for m in messages if m.get("type") == "tool_use"]
                text_messages = [m for m in messages if m.get("type") == "text"]
                
                assert len(tool_messages) >= 2
                assert len(text_messages) >= 1


@pytest.mark.unit
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
            
            with patch("app.services.orchestrator.anthropic.Anthropic") as mock_client:
                mock_response = MagicMock()
                mock_response.content = [TextBlock(type="text", text="Follow-up answer")]
                mock_response.stop_reason = "end_turn"
                mock_client.return_value.messages.create = MagicMock(return_value=mock_response)
                
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
                with patch("app.services.orchestrator.anthropic.Anthropic") as mock_client:
                    mock_response = MagicMock()
                    mock_response.content = [TextBlock(type="text", text="Answer")]
                    mock_response.stop_reason = "end_turn"
                    mock_client.return_value.messages.create = MagicMock(return_value=mock_response)
                    
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
            
            with patch("app.services.orchestrator.anthropic.Anthropic") as mock_client:
                mock_response = MagicMock()
                mock_response.content = [TextBlock(type="text", text="Test procedures include...")]
                mock_response.stop_reason = "end_turn"
                mock_client.return_value.messages.create = MagicMock(return_value=mock_response)
                
                messages = []
                async for msg in handle_conversation(
                    "conv-123",
                    "What about test procedures?",
                    faa_agent_config
                ):
                    messages.append(msg)
                
                # Claude should have received full history for context
                create_call = mock_client.return_value.messages.create.call_args
                messages_arg = create_call.kwargs.get("messages", [])
                
                # Should include prior conversation
                assert len(messages_arg) > 1


@pytest.mark.unit
class TestErrorHandling:
    """Tests for error handling."""
    
    @pytest.mark.asyncio
    async def test_handles_api_key_missing(self, faa_agent_config):
        """Test handling missing API key."""
        with patch("app.services.orchestrator.get_settings") as mock_settings:
            mock_settings.return_value.anthropic_api_key = None
            
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
    async def test_handles_claude_api_error(self, faa_agent_config):
        """Test handling Claude API errors."""
        with patch("app.services.orchestrator.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create = MagicMock(
                side_effect=Exception("API rate limit exceeded")
            )
            
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
class TestMultiAgentSupport:
    """Tests for multi-agent support (FAA, NRC, DoD)."""
    
    @pytest.mark.asyncio
    async def test_faa_agent_uses_faa_index(self, faa_agent_config):
        """Test FAA agent uses its own index."""
        with patch("app.services.orchestrator.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [TextBlock(type="text", text="FAA answer")]
            mock_response.stop_reason = "end_turn"
            mock_client.return_value.messages.create = MagicMock(return_value=mock_response)
            
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
                create_call = mock_client.return_value.messages.create.call_args
                system_arg = create_call.kwargs.get("system")
                assert "FAA certification expert" in system_arg
    
    @pytest.mark.asyncio
    async def test_nrc_agent_uses_nrc_index(self, nrc_agent_config):
        """Test NRC agent uses its own index."""
        with patch("app.services.orchestrator.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [TextBlock(type="text", text="NRC answer")]
            mock_response.stop_reason = "end_turn"
            mock_client.return_value.messages.create = MagicMock(return_value=mock_response)
            
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
                create_call = mock_client.return_value.messages.create.call_args
                system_arg = create_call.kwargs.get("system")
                assert "NRC regulatory expert" in system_arg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
