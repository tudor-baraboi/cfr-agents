#!/usr/bin/env python3
"""
Test local Ollama model with litellm
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import litellm

async def test_ollama():
    """Test Ollama model via litellm"""
    print("🧪 Testing Ollama with litellm...")
    print(f"Model: ollama/qwen2.5-coder:7b")
    print(f"Endpoint: http://localhost:11434")
    print()
    
    try:
        # Simple completion test
        print("📝 Sending test prompt...")
        response = await litellm.acompletion(
            model="ollama/qwen2.5-coder:7b",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": "Explain what FAA Part 25 is in one sentence."}
            ],
            api_base="http://localhost:11434",
            stream=False
        )
        
        print("✅ Response received!")
        print()
        print("Response:")
        print("=" * 60)
        content = response.choices[0].message.content
        print(content)
        print("=" * 60)
        print()
        print(f"Model used: {response.model}")
        print(f"Tokens: {response.usage.total_tokens if hasattr(response, 'usage') else 'N/A'}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Make sure Ollama is running: brew services list | grep ollama")
        print("2. Check model is pulled: ollama list")
        print("3. Verify endpoint: curl http://localhost:11434/api/tags")
        return False
    
    return True

if __name__ == "__main__":
    result = asyncio.run(test_ollama())
    sys.exit(0 if result else 1)
