"""
Claude orchestration loop with tool calling.

This is the core of the agent: receives user messages, calls Claude,
executes tools, and streams responses back.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import AsyncIterator, Any, Optional

import anthropic

from app.config import get_settings
from app.services.conversation import get_history, add_message
from app.agents import AgentConfig

logger = logging.getLogger(__name__)

# Retry configuration for transient API errors
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2.0  # seconds


async def execute_tool_with_config(
    name: str,
    input_data: dict[str, Any],
    agent_config: AgentConfig,
    fingerprint: Optional[str] = None,
    personal_doc_cache: Optional[dict[str, str]] = None,
) -> str:
    """
    Execute a tool by name using the agent's tool implementations.
    
    Automatically injects:
    - agent's search_index into tools that accept 'index_name' parameter
    - user's fingerprint into tools that accept 'fingerprint' parameter
    - personal_doc_cache into tools that accept it (for document grounding)
    """
    if name not in agent_config.tool_implementations:
        logger.warning(f"Unknown tool for agent {agent_config.name}: {name}")
        return f"Error: Unknown tool '{name}'"
    
    try:
        tool_func = agent_config.tool_implementations[name]
        sig = inspect.signature(tool_func)
        
        # Auto-inject agent's search index if tool accepts index_name parameter
        if "index_name" in sig.parameters and "index_name" not in input_data:
            input_data["index_name"] = agent_config.search_index
            logger.debug(f"Injected index_name={agent_config.search_index} into {name}")
        
        # Auto-inject user's fingerprint if tool accepts fingerprint parameter
        if "fingerprint" in sig.parameters and "fingerprint" not in input_data and fingerprint:
            input_data["fingerprint"] = fingerprint
            logger.debug(f"Injected fingerprint into {name}")
        
        # Auto-inject personal document cache if tool accepts it
        if "personal_doc_cache" in sig.parameters and personal_doc_cache is not None:
            input_data["personal_doc_cache"] = personal_doc_cache
            logger.debug(f"Injected personal_doc_cache into {name}")
        
        result = await tool_func(**input_data)
        # Ensure non-empty result (Claude API requires non-empty text content blocks)
        result_str = str(result) if result else ""
        if not result_str.strip():
            result_str = f"Tool {name} completed but returned no content."
        return result_str
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return f"Error executing {name}: {e}"


async def handle_conversation(
    conversation_id: str,
    user_message: str,
    agent_config: AgentConfig,
    fingerprint: Optional[str] = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Main orchestration loop:
    1. Load conversation history
    2. Call Claude with tools
    3. Execute any tool calls
    4. Stream responses back
    5. Save messages to history
    
    Args:
        conversation_id: Unique conversation identifier
        user_message: The user's message
        agent_config: Configuration for the agent (system prompt, tools, etc.)
        fingerprint: User's browser fingerprint (for personal document isolation)
    """
    settings = get_settings()
    
    if not settings.anthropic_api_key:
        yield {"type": "error", "content": "ANTHROPIC_API_KEY not configured"}
        return
    
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    
    # Conversation-scoped cache for personal document content (for grounding)
    personal_doc_cache: dict[str, str] = {}
    
    # Load conversation history and add user message
    messages = get_history(conversation_id).copy()
    messages.append({"role": "user", "content": user_message})
    
    # Estimate token count and warn if approaching limit
    # Rough approximation: ~4 chars per token (conservative estimate)
    def estimate_tokens(msgs: list, system: str) -> int:
        total_chars = len(system)
        for msg in msgs:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        # Tool results can be nested
                        total_chars += len(str(block))
        return total_chars // 4
    
    estimated_tokens = estimate_tokens(messages, agent_config.system_prompt)
    TOKEN_WARNING_THRESHOLD = 150000
    TOKEN_LIMIT = 200000
    
    if estimated_tokens > TOKEN_WARNING_THRESHOLD:
        warning_pct = int((estimated_tokens / TOKEN_LIMIT) * 100)
        yield {
            "type": "warning",
            "content": f"⚠️ This conversation is using ~{warning_pct}% of the context limit ({estimated_tokens:,} / {TOKEN_LIMIT:,} tokens). Consider starting a new conversation to avoid errors."
        }
        logger.warning(f"Conversation {conversation_id} approaching token limit: ~{estimated_tokens:,} tokens")
    
    # Get tools from agent config
    tool_definitions = agent_config.tool_definitions if agent_config.tool_definitions else None
    
    logger.info(f"[agent={agent_config.name}] Starting conversation {conversation_id}")
    
    # Tool execution loop
    iteration = 0
    while True:
        iteration += 1
        logger.info(f"[iter={iteration}] Calling Claude with {len(messages)} messages")
        
        # Retry loop for transient API errors
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                # Stream response from Claude
                text_chunks = []
                chunk_count = 0
                
                # Use Extended Thinking with interleaved thinking for reasoning between tool calls
                # The beta header enables thinking blocks to appear after tool results, not just at start
                async with client.messages.stream(
                    model=settings.anthropic_model,
                    max_tokens=16384,
                    system=agent_config.system_prompt,
                    messages=messages,
                    tools=tool_definitions if tool_definitions else anthropic.NOT_GIVEN,
                    thinking={
                        "type": "enabled",
                        "budget_tokens": 10000,  # Budget spans all thinking blocks with interleaved
                    },
                    extra_headers={
                        "anthropic-beta": "interleaved-thinking-2025-05-14"
                    },
                ) as stream:
                    thinking_chunks = []
                    
                    # Meta-commentary filter with streaming:
                    # Stream text normally for good UX, but track if we're in a text block.
                    # If tool_use starts right after text, send a "clear_text" event to
                    # tell the frontend to remove the meta-commentary we already streamed.
                    current_text_block_chars = 0  # Track chars in current text block
                    in_text_block = False
                    
                    async for event in stream:
                        if event.type == "content_block_start":
                            if hasattr(event.content_block, "type"):
                                block_type = event.content_block.type
                                if block_type == "thinking":
                                    logger.debug(f"[iter={iteration}] Thinking block starting")
                                    current_text_block_chars = 0
                                    in_text_block = False
                                elif block_type == "text":
                                    logger.debug(f"[iter={iteration}] Text block starting")
                                    current_text_block_chars = 0
                                    in_text_block = True
                                elif block_type == "tool_use":
                                    logger.info(f"[iter={iteration}] Tool use starting: {event.content_block.name}")
                                    # Tool use right after text = meta-commentary
                                    # Tell frontend to clear the text we just streamed
                                    if current_text_block_chars > 0:
                                        logger.info(f"[iter={iteration}] Sending clear_text for {current_text_block_chars} chars of meta-commentary")
                                        yield {"type": "clear_text", "chars": current_text_block_chars}
                                    current_text_block_chars = 0
                                    in_text_block = False
                                    yield {
                                        "type": "tool_start",
                                        "tool": event.content_block.name,
                                    }
                        
                        elif event.type == "content_block_delta":
                            if hasattr(event.delta, "type"):
                                delta_type = event.delta.type
                                logger.debug(f"[iter={iteration}] Delta type: {delta_type}")
                                if delta_type == "thinking_delta":
                                    # Extended Thinking: reasoning content
                                    thinking_text = event.delta.thinking
                                    thinking_chunks.append(thinking_text)
                                    print(f"!!!THINKING!!! iter={iteration} len={len(thinking_text)}", flush=True)
                                    logger.info(f"[iter={iteration}] Yielding thinking chunk: {len(thinking_text)} chars")
                                    yield {"type": "thinking", "content": thinking_text}
                                elif delta_type == "signature_delta":
                                    # Signature for thinking block verification (required for preservation)
                                    logger.debug(f"[iter={iteration}] Received thinking block signature")
                                elif delta_type == "text_delta":
                                    # Stream text immediately for good UX
                                    chunk_count += 1
                                    text = event.delta.text
                                    text_chunks.append(text)
                                    if in_text_block:
                                        current_text_block_chars += len(text)
                                    yield {"type": "text", "content": text}
                                elif delta_type == "input_json_delta":
                                    yield {"type": "tool_input", "partial": event.delta.partial_json}
                        
                        elif event.type == "content_block_stop":
                            # Text block ended - reset counter but keep the value
                            # (we need it if tool_use starts next)
                            if not in_text_block:
                                current_text_block_chars = 0
                            in_text_block = False
                        
                        elif event.type == "message_stop":
                            # Reset for next iteration
                            current_text_block_chars = 0
                            logger.info(f"[iter={iteration}] Message stopped")
                        
                    response = await stream.get_final_message()
                    
                    # Log thinking summary
                    total_thinking = "".join(thinking_chunks)
                    if total_thinking:
                        logger.info(f"[iter={iteration}] Thinking: {len(total_thinking)} chars")
                
                # Log response details
                total_text = "".join(text_chunks)
                output_tokens = response.usage.output_tokens if hasattr(response, 'usage') else 'unknown'
                logger.info(f"[iter={iteration}] Stream complete: {chunk_count} chunks, {len(total_text)} chars, output_tokens={output_tokens}, stop_reason={response.stop_reason}")
                if response.stop_reason == "max_tokens":
                    logger.warning(f"[iter={iteration}] Response truncated due to max_tokens! output_tokens={output_tokens}")
                
                # Success - break out of retry loop
                last_error = None
                break
                
            except anthropic.APIStatusError as e:
                last_error = e
                # Retry on overloaded (529) or rate limit (429) errors
                if e.status_code in (429, 529) and attempt < MAX_RETRIES - 1:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Claude API overloaded/rate limited (status {e.status_code}), retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    yield {"type": "text", "content": f"\n\n*API busy, retrying in {int(delay)}s...*\n\n"}
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Claude API error: {e}")
                    yield {"type": "error", "content": f"Claude API error: {e.message}"}
                    return
                    
            except anthropic.APIError as e:
                last_error = e
                # Check if the error body indicates an overloaded error (can come without status code)
                is_overloaded = False
                if hasattr(e, 'body') and isinstance(e.body, dict):
                    error_info = e.body.get('error', {})
                    if isinstance(error_info, dict) and error_info.get('type') == 'overloaded_error':
                        is_overloaded = True
                
                if is_overloaded and attempt < MAX_RETRIES - 1:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Claude API overloaded (from body), retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    yield {"type": "text", "content": f"\n\n*API busy, retrying in {int(delay)}s...*\n\n"}
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Claude API error: {e}")
                    yield {"type": "error", "content": f"Claude API error: {e}"}
                return
        
        # If we exhausted retries with an error
        if last_error:
            yield {"type": "error", "content": f"Claude API unavailable after {MAX_RETRIES} retries: {last_error.message}"}
            return
        
        # Check for tool calls
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        
        if not tool_uses:
            # No tools called, we're done
            break
        
        # Add assistant message to history
        messages.append({"role": "assistant", "content": response.content})
        
        # Execute tools and collect results
        tool_results = []
        for tool_use in tool_uses:
            logger.info(f"Executing tool: {tool_use.name}")
            yield {"type": "tool_executing", "tool": tool_use.name, "input": tool_use.input}
            
            result = await execute_tool_with_config(
                tool_use.name, tool_use.input, agent_config, fingerprint, personal_doc_cache
            )
            
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })
            
            yield {"type": "tool_result", "tool": tool_use.name, "result": result[:500]}  # Truncate for UI
        
        # Add tool results to continue conversation
        messages.append({"role": "user", "content": tool_results})
    
    # Save final conversation state
    add_message(conversation_id, {"role": "user", "content": user_message})
    add_message(conversation_id, {"role": "assistant", "content": response.content})
    
    logger.info(f"Conversation {conversation_id} completed")
