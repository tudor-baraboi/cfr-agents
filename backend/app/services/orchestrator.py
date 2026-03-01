"""
LLM orchestration loop with tool calling via litellm.

This is the core of the agent: receives user messages, calls LLM via litellm,
executes tools, and streams responses back. Supports multiple LLM providers
(Anthropic, Ollama, OpenAI, etc.) via litellm abstraction.

Key for Ollama tool calling:
- Use 'ollama_chat/' prefix (not 'ollama/') for proper tool support
- Non-streaming is more reliable for tool calls with Ollama
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import AsyncIterator, Any, Optional

import litellm

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
        result_str = str(result) if result else ""
        if not result_str.strip():
            result_str = f"Tool {name} completed but returned no content."
        return result_str
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return f"Error executing {name}: {e}"


def convert_tools_to_openai_format(tool_definitions: list[dict]) -> list[dict]:
    """Convert Anthropic-style tool definitions to OpenAI function calling format."""
    openai_tools = []
    for tool in tool_definitions:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            }
        })
    return openai_tools


async def handle_conversation(
    conversation_id: str,
    user_message: str,
    agent_config: AgentConfig,
    fingerprint: Optional[str] = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Main orchestration loop:
    1. Load conversation history
    2. Call LLM with tools
    3. Execute any tool calls
    4. Stream responses back
    5. Save messages to history
    """
    settings = get_settings()
    
    # Determine which LLM provider to use
    use_ollama = bool(settings.ollama_model)
    if use_ollama:
        # Use ollama_chat/ prefix for proper tool calling support
        model_id = f"ollama_chat/{settings.ollama_model}"
        api_base = settings.ollama_base_url
        logger.info(f"Using Ollama model: {settings.ollama_model} at {api_base}")
    else:
        if not settings.anthropic_api_key:
            yield {"type": "error", "content": "ANTHROPIC_API_KEY not configured"}
            return
        model_id = f"anthropic/{settings.llm_model}"
        api_base = None
        logger.info(f"Using Anthropic model: {settings.llm_model}")
    
    system_prompt = agent_config.system_prompt
    litellm.set_verbose = False
    personal_doc_cache: dict[str, str] = {}
    
    messages = get_history(conversation_id).copy()
    messages.append({"role": "user", "content": user_message})
    
    # Token estimation
    def estimate_tokens(msgs: list, system: str) -> int:
        total_chars = len(system)
        for msg in msgs:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total_chars += len(str(block))
        return total_chars // 4
    
    estimated_tokens = estimate_tokens(messages, system_prompt)
    if estimated_tokens > 150000:
        warning_pct = int((estimated_tokens / 200000) * 100)
        yield {
            "type": "warning",
            "content": f"Context is {warning_pct}% full. Consider starting a new conversation."
        }
    
    # Convert tools to OpenAI format
    tool_definitions = None
    if agent_config.tool_definitions:
        tool_definitions = convert_tools_to_openai_format(agent_config.tool_definitions)
    
    logger.info(f"[agent={agent_config.name}] Starting conversation {conversation_id}")
    
    all_text_chunks = []
    iteration = 0
    max_iterations = 10
    
    while iteration < max_iterations:
        iteration += 1
        logger.info(f"[iter={iteration}] Calling LLM with {len(messages)} messages")
        
        last_error = None
        text_chunks = []
        tool_calls = []
        finish_reason = None
        
        for attempt in range(MAX_RETRIES):
            try:
                chunk_count = 0
                
                # Build API params - unified for all providers via litellm
                api_params = {
                    "model": model_id,
                    "max_tokens": 16384,
                    "messages": [{"role": "system", "content": system_prompt}] + messages,
                    "timeout": settings.llm_request_timeout_seconds,
                }
                
                if tool_definitions:
                    api_params["tools"] = tool_definitions
                    # Force tool use on first turn for Ollama (small models need encouragement)
                    if use_ollama and iteration == 1:
                        api_params["tool_choice"] = "required"
                    else:
                        api_params["tool_choice"] = "auto"
                
                # Provider-specific settings
                if use_ollama:
                    api_params["api_base"] = api_base
                    # Non-streaming is more reliable for Ollama tool calls
                    api_params["stream"] = not bool(tool_definitions)
                else:
                    # Anthropic: enable extended thinking and streaming
                    api_params["stream"] = True
                    if "anthropic" in model_id.lower() or "claude" in model_id.lower():
                        api_params["thinking"] = {"type": "enabled", "budget_tokens": 10000}
                        api_params["extra_headers"] = {"anthropic-beta": "interleaved-thinking-2025-05-14"}
                
                if api_params.get("stream", False):
                    # Streaming mode (Anthropic, or Ollama without tools)
                    stream_response = await litellm.acompletion(**api_params)
                    
                    current_tool_call = None
                    tool_call_args = ""
                    
                    stream_iter = stream_response.__aiter__()
                    while True:
                        try:
                            event = await asyncio.wait_for(
                                stream_iter.__anext__(),
                                timeout=settings.llm_stream_chunk_timeout_seconds,
                            )
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            logger.error("LLM stream timeout")
                            yield {"type": "error", "content": "LLM response timed out."}
                            return
                        
                        if hasattr(event, 'choices') and event.choices:
                            choice = event.choices[0]
                            
                            if hasattr(choice, 'finish_reason') and choice.finish_reason:
                                finish_reason = choice.finish_reason
                            
                            if hasattr(choice, 'delta'):
                                delta = choice.delta
                                
                                content = getattr(delta, 'content', None)
                                if content:
                                    chunk_count += 1
                                    text_chunks.append(content)
                                    all_text_chunks.append(content)
                                    yield {"type": "text", "content": content}
                                
                                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                                    for tc in delta.tool_calls:
                                        if tc.id:
                                            if current_tool_call and tool_call_args:
                                                try:
                                                    current_tool_call["arguments"] = json.loads(tool_call_args)
                                                except json.JSONDecodeError:
                                                    current_tool_call["arguments"] = {"raw": tool_call_args}
                                                tool_calls.append(current_tool_call)
                                            
                                            current_tool_call = {
                                                "id": tc.id,
                                                "name": tc.function.name if tc.function else None,
                                                "arguments": {}
                                            }
                                            tool_call_args = ""
                                            logger.info(f"[iter={iteration}] Tool call: {current_tool_call['name']}")
                                        
                                        if tc.function and tc.function.name and current_tool_call:
                                            current_tool_call["name"] = tc.function.name
                                        
                                        if tc.function and tc.function.arguments:
                                            tool_call_args += tc.function.arguments
                    
                    if current_tool_call:
                        if tool_call_args:
                            try:
                                current_tool_call["arguments"] = json.loads(tool_call_args)
                            except json.JSONDecodeError:
                                current_tool_call["arguments"] = {"raw": tool_call_args}
                        tool_calls.append(current_tool_call)
                
                else:
                    # Non-streaming mode (Ollama with tools - more reliable)
                    response = await litellm.acompletion(**api_params)
                    
                    message = response.choices[0].message
                    finish_reason = response.choices[0].finish_reason
                    
                    # Extract text content
                    if message.content:
                        text_chunks.append(message.content)
                        all_text_chunks.append(message.content)
                        yield {"type": "text", "content": message.content}
                        chunk_count = 1
                    
                    # Extract tool calls
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        for tc in message.tool_calls:
                            tool_call = {
                                "id": tc.id or f"call_{iteration}_{len(tool_calls)}",
                                "name": tc.function.name,
                                "arguments": {},
                            }
                            # Parse arguments
                            if tc.function.arguments:
                                if isinstance(tc.function.arguments, str):
                                    try:
                                        tool_call["arguments"] = json.loads(tc.function.arguments)
                                    except json.JSONDecodeError:
                                        tool_call["arguments"] = {"raw": tc.function.arguments}
                                else:
                                    tool_call["arguments"] = tc.function.arguments
                            logger.info(f"[iter={iteration}] Tool call: {tool_call['name']}")
                            tool_calls.append(tool_call)
                
                logger.info(f"[iter={iteration}] Complete: {chunk_count} chunks, {len(tool_calls)} tools, finish={finish_reason}")
                last_error = None
                break
                
            except (litellm.RateLimitError, litellm.APIError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"API error, retrying in {delay}s")
                    yield {"type": "text", "content": f"\n\n*Retrying in {int(delay)}s...*\n\n"}
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"API error: {e}")
                    yield {"type": "error", "content": f"API error: {e}"}
                    return
                    
            except litellm.APIConnectionError as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Connection error, retrying: {e}")
                    yield {"type": "text", "content": "\n\n*Connection error, retrying...*\n\n"}
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Connection error: {e}")
                    yield {"type": "error", "content": f"Connection error: {e}"}
                    return
        
        if last_error:
            yield {"type": "error", "content": f"API unavailable after {MAX_RETRIES} retries"}
            return
        
        # Only break if no tool calls - ignore finish_reason for tool-capable models
        if not tool_calls:
            logger.info(f"[iter={iteration}] Conversation complete (no tool calls)")
            break
        
        # Add assistant message with tool calls
        assistant_message = {
            "role": "assistant",
            "content": "".join(text_chunks) if text_chunks else None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]) if isinstance(tc["arguments"], dict) else str(tc["arguments"])
                    }
                }
                for tc in tool_calls
            ]
        }
        messages.append(assistant_message)
        
        # Execute tools
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["arguments"]
            tool_id = tool_call["id"]
            
            logger.info(f"Executing tool: {tool_name}")
            yield {"type": "tool_executing", "tool": tool_name, "input": tool_args}
            
            result = await execute_tool_with_config(
                tool_name, tool_args, agent_config, fingerprint, personal_doc_cache
            )
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result,
            })
            
            result_preview = result[:500] + "..." if len(result) > 500 else result
            yield {"type": "tool_result", "tool": tool_name, "result": result_preview}
        
        text_chunks = []
    
    if iteration >= max_iterations:
        yield {"type": "warning", "content": "Max iterations reached."}
    
    final_text = "".join(all_text_chunks)
    add_message(conversation_id, {"role": "user", "content": user_message})
    add_message(conversation_id, {"role": "assistant", "content": final_text})
    
    logger.info(f"Conversation {conversation_id} completed")
