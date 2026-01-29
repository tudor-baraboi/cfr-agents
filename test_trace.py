"""Test script to trace NRC agent tool calls."""
import asyncio
import json
import websockets


async def test_nrc_agent():
    """Run a full trace of the NRC agent."""
    # Connect to the backend WebSocket
    uri = "ws://localhost:8000/ws/chat/test-trace-002?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb2RlIjoiQURNSU4tVFVET1IiLCJpc19hZG1pbiI6dHJ1ZSwiZXhwIjoxNzcxNDAwNzExLCJpYXQiOjE3Njg4MDg3MTF9.LNz2HJPwDc216oX5jJo7OIOsitgfKBOp4g3fDQtNKuA&agent=nrc"
    
    print("=" * 70)
    print("NRC AGENT FULL TRACE")
    print("=" * 70)
    
    async with websockets.connect(uri) as ws:
        # Send a test question
        question = "What are the Part 21 reporting requirements for nuclear component defects?"
        print(f"\nUSER QUESTION: {question}\n")
        print("-" * 70)
        
        await ws.send(json.dumps({
            "message": question
        }))
        
        # Collect all events
        tool_calls = []
        text_chunks = []
        current_tool = None
        tool_count = 0
        
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=120)
                data = json.loads(msg)
                
                if data["type"] == "tool_start":
                    tool_count += 1
                    current_tool = {"name": data["tool"], "input": "", "num": tool_count}
                    print(f"\n[TOOL {tool_count}] START: {data['tool']}")
                
                elif data["type"] == "tool_input":
                    if current_tool:
                        current_tool["input"] += data.get("partial", "")
                
                elif data["type"] == "tool_end":
                    if current_tool:
                        try:
                            input_json = json.loads(current_tool["input"]) if current_tool["input"] else {}
                            current_tool["input"] = input_json
                        except:
                            pass
                        tool_calls.append(current_tool)
                        print(f"[TOOL {current_tool['num']}] INPUT: {json.dumps(current_tool['input'], indent=2)}")
                        result_preview = data.get("result", "")[:500]
                        print(f"[TOOL {current_tool['num']}] RESULT (first 500 chars):\n{result_preview}\n")
                        current_tool = None
                
                elif data["type"] == "text":
                    text_chunks.append(data["content"])
                
                elif data["type"] == "done":
                    print("\n" + "-" * 70)
                    print("CONVERSATION COMPLETE")
                    break
                
                elif data["type"] == "error":
                    print(f"\nERROR: {data['content']}")
                    break
                    
            except asyncio.TimeoutError:
                print("Timeout waiting for response")
                break
        
        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Total tool calls: {len(tool_calls)}")
        for i, tc in enumerate(tool_calls, 1):
            print(f"  {i}. {tc['name']}")
            if isinstance(tc['input'], dict):
                for k, v in tc['input'].items():
                    print(f"      {k}: {str(v)[:80]}")
        
        full_response = "".join(text_chunks)
        print(f"\nResponse length: {len(full_response)} chars")
        print(f"\n--- FULL RESPONSE ---")
        print(full_response[:2000])
        if len(full_response) > 2000:
            print(f"\n... [truncated, {len(full_response) - 2000} more chars]")


if __name__ == "__main__":
    asyncio.run(test_nrc_agent())
