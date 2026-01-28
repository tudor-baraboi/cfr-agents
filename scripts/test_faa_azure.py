#!/usr/bin/env python3
"""Test FAA agent on Azure backend with tool tracing."""

import asyncio
import json
import httpx
import websockets

AZURE_BACKEND = "https://faa-agent-api.azurewebsites.net"
AUTH_CODE = "ADMIN-TUDOR"

async def get_auth_token() -> str:
    """Get JWT token from Azure backend."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AZURE_BACKEND}/auth/validate-code",
            json={"code": AUTH_CODE}
        )
        response.raise_for_status()
        return response.json()["token"]

async def test_faa_agent():
    """Connect to FAA agent and trace tool usage."""
    print("Getting auth token...")
    token = await get_auth_token()
    print(f"Got token: {token[:20]}...")
    
    # Generate conversation ID
    import uuid
    conversation_id = str(uuid.uuid4())
    
    # Connect with agent=faa
    ws_url = f"wss://faa-agent-api.azurewebsites.net/ws/chat/{conversation_id}?agent=faa&token={token}"
    print(f"Connecting to: {ws_url[:50]}...")
    
    tools_used = []
    
    async with websockets.connect(ws_url) as ws:
        # Send test question about FAA regulations
        question = "What are the HIRF protection requirements for aircraft?"
        print(f"\n{'='*60}")
        print(f"QUESTION: {question}")
        print(f"{'='*60}\n")
        
        await ws.send(json.dumps({"message": question}))
        
        # Collect responses
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=120)
                data = json.loads(msg)
                
                if data.get("type") == "tool_start":
                    tool_name = data.get("tool", "unknown")
                    tool_input = data.get("input", {})
                    tools_used.append(tool_name)
                    print(f"🔧 TOOL START: {tool_name}")
                    print(f"   Input: {json.dumps(tool_input)[:100]}")
                    print()
                    
                elif data.get("type") == "tool_result":
                    tool_name = data.get("tool", "unknown")
                    result = data.get("result", "")
                    print(f"✅ TOOL RESULT: {tool_name}")
                    print(f"   Result: {result[:300]}...")
                    print()
                    
                elif data.get("type") == "done":
                    break
                    
                elif data.get("type") == "error":
                    print(f"❌ ERROR: {data.get('message')}")
                    break
                    
            except asyncio.TimeoutError:
                print("Timeout waiting for response")
                break
    
    # Summary
    print(f"\n{'='*60}")
    print("TRACE SUMMARY")
    print(f"{'='*60}")
    print(f"\nTools Used ({len(tools_used)}):")
    for i, tool in enumerate(tools_used, 1):
        print(f"  {i}. {tool}")

if __name__ == "__main__":
    asyncio.run(test_faa_agent())
