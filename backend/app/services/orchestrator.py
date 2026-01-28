"""
Claude orchestration loop with tool calling.

This is the core of the agent: receives user messages, calls Claude,
executes tools, and streams responses back.
"""

import asyncio
import inspect
import logging
from typing import AsyncIterator, Any

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
) -> str:
    """
    Execute a tool by name using the agent's tool implementations.
    
    Automatically injects the agent's search_index into tools that accept
    an 'index_name' parameter, enabling context-aware index routing.
    """
    if name not in agent_config.tool_implementations:
        logger.warning(f"Unknown tool for agent {agent_config.name}: {name}")
        return f"Error: Unknown tool '{name}'"
    
    try:
        tool_func = agent_config.tool_implementations[name]
        
        # Auto-inject agent's search index if tool accepts index_name parameter
        sig = inspect.signature(tool_func)
        if "index_name" in sig.parameters and "index_name" not in input_data:
            input_data["index_name"] = agent_config.search_index
            logger.debug(f"Injected index_name={agent_config.search_index} into {name}")
        
        result = await tool_func(**input_data)
        return str(result)
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return f"Error executing {name}: {e}"


async def handle_conversation(
    conversation_id: str,
    user_message: str,
    agent_config: AgentConfig,
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
    """
    settings = get_settings()
    
    if not settings.anthropic_api_key:
        yield {"type": "error", "content": "ANTHROPIC_API_KEY not configured"}
        return
    
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    
    # Load conversation history and add user message
    messages = get_history(conversation_id).copy()
    messages.append({"role": "user", "content": user_message})
    
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
                
                async with client.messages.stream(
                    model=settings.anthropic_model,
                    max_tokens=16384,
                    system=agent_config.system_prompt,
                    messages=messages,
                    tools=tool_definitions if tool_definitions else anthropic.NOT_GIVEN,
                ) as stream:
                    async for event in stream:
                        if event.type == "content_block_start":
                            if hasattr(event.content_block, "text"):
                                logger.debug(f"[iter={iteration}] Text block starting")
                            elif hasattr(event.content_block, "name"):
                                # Tool use starting
                                logger.info(f"[iter={iteration}] Tool use starting: {event.content_block.name}")
                                yield {
                                    "type": "tool_start",
                                    "tool": event.content_block.name,
                                }
                        
                        elif event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                chunk_count += 1
                                text_chunks.append(event.delta.text)
                                yield {"type": "text", "content": event.delta.text}
                            elif hasattr(event.delta, "partial_json"):
                                yield {"type": "tool_input", "partial": event.delta.partial_json}
                        
                        elif event.type == "message_stop":
                            logger.info(f"[iter={iteration}] Message stopped")
                        
                    response = await stream.get_final_message()
                
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
            
            result = await execute_tool_with_config(tool_use.name, tool_use.input, agent_config)
            
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
