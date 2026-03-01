"""Quick WebSocket test for the FAA Agent with litellm tool calling."""

import asyncio
import json
import sys
import httpx
import websockets


async def get_auth_token() -> str:
    """Get JWT token via fingerprint endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://127.0.0.1:8000/auth/fingerprint",
            json={"visitor_id": "test-fingerprint-123"}
        )
        response.raise_for_status()
        return response.json()["token"]


async def test_chat(user_message: str):
    # Get auth token first
    token = await get_auth_token()
    print(f"Got auth token: {token[:20]}...")
    
    uri = f"ws://127.0.0.1:8000/ws/chat/test-conv-123?token={token}&agent=faa"
    
    async with websockets.connect(uri) as ws:
        # Send a test message
        message = {"message": user_message}
        print(f"\n>>> Sending: {message['message']}\n")
        await ws.send(json.dumps(message))
        
        # Receive streamed response
        while True:
            response = await ws.recv()
            data = json.loads(response)
            
            if data["type"] == "text":
                print(data["content"], end="", flush=True)
            elif data["type"] == "ping":
                pass  # Ignore keep-alive pings
            elif data["type"] == "tool_start":
                print(f"\n[Calling tool: {data['tool']}]")
            elif data["type"] == "tool_executing":
                print(f"\n[Executing: {data['tool']}]")
            elif data["type"] == "tool_result":
                print(f"\n[Tool result received: {len(data.get('result', ''))} chars]\n")
            elif data["type"] == "done":
                print("\n\n>>> Done")
                break
            elif data["type"] == "error":
                print(f"\n>>> Error: {data['content']}")
                break


if __name__ == "__main__":
    user_message = sys.argv[1] if len(sys.argv) > 1 else "What is CFR section 25.1309 about?"
    asyncio.run(test_chat(user_message))
