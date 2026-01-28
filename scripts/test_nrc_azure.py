#!/usr/bin/env python3
"""Test NRC agent on Azure backend and trace tool usage."""

import asyncio
import websockets
import json
import uuid
import requests

BASE_URL = "https://faa-agent-api.azurewebsites.net"
ADMIN_CODE = "ADMIN-TUDOR"

def get_auth_token():
    """Get JWT token by validating admin code."""
    resp = requests.post(
        f"{BASE_URL}/auth/validate-code",
        json={"code": ADMIN_CODE}
    )
    resp.raise_for_status()
    return resp.json()["token"]

async def test_nrc_agent():
    # Get auth token first
    print("Getting auth token...")
    token = get_auth_token()
    print(f"Got token: {token[:50]}...")
    
    conversation_id = str(uuid.uuid4())
    # Agent is specified via query parameter
    uri = f"wss://faa-agent-api.azurewebsites.net/ws/chat/{conversation_id}?agent=nrc&token={token}"
    
    print(f"\nConnecting to: wss://.../{conversation_id}?agent=nrc&token=...")
    print("=" * 60)
    
    async with websockets.connect(uri) as ws:
        # Send a test question that should trigger CFR reference following
        question = "What are the Part 21 reporting requirements under 10 CFR 21.21?"
        print(f"QUESTION: {question}")
        print("=" * 60)
        
        # Backend expects {"message": "..."} format
        await ws.send(json.dumps({
            "message": question
        }))
        
        tools_used = []
        full_response = []
        
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=120)
                data = json.loads(msg)
                
                msg_type = data.get("type", "")
                
                if msg_type == "tool_start":
                    tool_name = data.get("tool", "unknown")
                    tool_input = data.get("input", {})
                    tools_used.append({"name": tool_name, "input": tool_input})
                    print(f"\n🔧 TOOL START: {tool_name}")
                    print(f"   Input: {json.dumps(tool_input, indent=2)[:500]}")
                    
                elif msg_type == "tool_result":
                    tool_name = data.get("tool", "unknown")
                    result = data.get("result", "")
                    print(f"\n✅ TOOL RESULT: {tool_name}")
                    result_preview = str(result)[:1000]
                    print(f"   Result: {result_preview}")
                    if len(str(result)) > 1000:
                        print("   ... (truncated)")
                    
                elif msg_type == "content":
                    content = data.get("content", "")
                    if content:
                        full_response.append(content)
                        print(content, end="", flush=True)
                        
                elif msg_type == "done":
                    print("\n\n" + "=" * 60)
                    print("TRACE SUMMARY")
                    print("=" * 60)
                    print(f"\nTools Used ({len(tools_used)}):")
                    for i, t in enumerate(tools_used, 1):
                        print(f"  {i}. {t['name']}")
                        if t['input']:
                            inp = json.dumps(t['input'])
                            print(f"     Input: {inp[:300]}")
                    break
                    
                elif msg_type == "error":
                    print(f"\n❌ ERROR: {data.get('content', 'Unknown error')}")
                    break
                    
            except asyncio.TimeoutError:
                print("\n⏰ Timeout waiting for response")
                break
            except Exception as e:
                print(f"\n❌ Exception: {e}")
                break

if __name__ == "__main__":
    asyncio.run(test_nrc_agent())
