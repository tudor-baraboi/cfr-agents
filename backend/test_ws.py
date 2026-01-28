"""Quick WebSocket test for the FAA Agent."""

import asyncio
import json
import sys
import websockets


async def test_chat(user_message: str):
    uri = "ws://127.0.0.1:8000/ws/chat/test-123"
    
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
            elif data["type"] == "tool_start":
                print(f"\n[Calling tool: {data['tool']}]")
            elif data["type"] == "tool_executing":
                print(f"[Executing: {data['tool']} with {data['input']}]")
            elif data["type"] == "tool_result":
                print(f"[Tool result received: {len(data['result'])} chars]\n")
            elif data["type"] == "done":
                print("\n\n>>> Done")
                break
            elif data["type"] == "error":
                print(f"\n>>> Error: {data['content']}")
                break


if __name__ == "__main__":
    user_message = sys.argv[1] if len(sys.argv) > 1 else "What is CFR section 25.1309 about?"
    asyncio.run(test_chat(user_message))
