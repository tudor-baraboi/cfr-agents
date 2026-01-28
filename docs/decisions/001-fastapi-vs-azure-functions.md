# Decision: FastAPI vs Azure Functions

**Date:** January 2025  
**Status:** Decided — FastAPI  
**Context:** Choosing backend runtime for FAA Agent

## Options Considered

### Option A: FastAPI on Azure App Service ✅ Chosen
- Native WebSocket support for real-time streaming
- Stream Claude tokens directly to client
- Simple mental model, easy local development
- No cold starts (always running)
- Cost: ~$13-50/month for basic tier

### Option B: Azure Functions + SignalR
- Functions handle business logic
- SignalR Service handles real-time communication
- More Azure-native, but adds complexity
- Extra service to manage and pay for

### Option C: Azure Functions + HTTP Streaming (SSE)
- Skip WebSocket, use Server-Sent Events
- Simpler than SignalR
- One-directional streaming (server → client)
- Client sends messages via regular HTTP POST
- Could revisit if cost becomes a concern

## Key Factors

| Aspect | FastAPI | Azure Functions |
|--------|---------|-----------------|
| WebSocket support | Native, full-duplex | ❌ Needs SignalR |
| Streaming responses | Built-in async generators | Limited |
| Long-running requests | No timeout issues | 10 min max (Consumption) |
| Local dev | Simple `uvicorn --reload` | Requires Functions Core Tools |
| Cold starts | None | Can be slow |
| Cost | Pay for always-on | Pay per execution |

## Decision

**FastAPI on App Service** — chosen for simplicity and native WebSocket/streaming support.

## Revisit If
- Traffic is very low and cost matters more than latency
- Need to integrate with other Azure event-driven services
- Team has strong Azure Functions expertise
