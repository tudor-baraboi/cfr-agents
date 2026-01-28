import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from app.config import get_settings
from app.routers import health, auth, feedback, admin
from app.routers.auth import decode_jwt_token
from app.services.orchestrator import handle_conversation
from app.services.usage import get_usage_tracker
from app.services.geolocation import extract_client_ip
from app.agents import get_agent_config

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logger.info("FAA Agent starting up")
    
    # Validate required settings for auth
    if not settings.jwt_secret:
        logger.warning("JWT_SECRET not set - authentication will not work!")
    
    yield
    
    # Clean up usage tracker
    tracker = get_usage_tracker()
    await tracker.close()
    
    logger.info("FAA Agent shutting down")


app = FastAPI(
    title="FAA Agent API",
    description="Conversational AI agent for FAA regulations",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(feedback.router)
app.include_router(admin.router)


@app.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket, 
    conversation_id: str,
    token: str = Query(default=None),
    agent: str = Query(default="faa"),
):
    """
    WebSocket endpoint for chat conversations.
    
    Requires a valid JWT token as query parameter.
    Receives: {"message": "user question"}
    Sends: {"type": "text", "content": "..."} or {"type": "tool_call", ...}
    
    Args:
        conversation_id: Unique conversation identifier
        token: JWT authentication token
        agent: Agent type - 'faa' (default) or 'nrc'
    """
    settings = get_settings()
    
    # Validate and get agent config
    try:
        agent_config = get_agent_config(agent)
    except ValueError as e:
        await websocket.close(code=4000, reason=str(e))
        return
    
    # Validate token
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return
    
    payload = decode_jwt_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
    
    # Extract auth info - supports both fingerprint and admin code auth
    fingerprint = payload.get("fingerprint")
    code = payload.get("code", "")
    is_admin = payload.get("is_admin", False)
    
    # Determine user identifier for logging
    user_id = code[:8] if is_admin else (fingerprint[:8] if fingerprint else "unknown")
    
    # Extract client IP and user agent for tracking
    forwarded_for = websocket.headers.get("x-forwarded-for")
    remote_addr = websocket.client.host if websocket.client else None
    client_ip = extract_client_ip(forwarded_for, remote_addr)
    user_agent = websocket.headers.get("user-agent", "")
    
    # Check daily quota for non-admin users
    tracker = get_usage_tracker()
    if not is_admin:
        if not fingerprint:
            await websocket.close(code=4001, reason="Invalid token - missing fingerprint")
            return
        
        allowed, used, remaining = await tracker.check_quota(fingerprint)
        if not allowed:
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "content": f"You've used your {settings.daily_request_limit} daily queries. Come back tomorrow!"
            })
            await websocket.close(code=4003, reason="Daily quota exceeded")
            return
    
    await websocket.accept()
    logger.info(f"WebSocket connected: {conversation_id} (agent={agent_config.name}, user={user_id}..., admin={is_admin})")
    
    # Keep-alive task to prevent idle timeout
    async def keep_alive():
        """Send periodic pings to keep the connection alive."""
        try:
            while True:
                await asyncio.sleep(20)  # Ping every 20 seconds
                if websocket.client_state == WebSocketState.CONNECTED:
                    try:
                        await websocket.send_json({"type": "ping"})
                    except Exception:
                        break
                else:
                    break
        except asyncio.CancelledError:
            pass
    
    keep_alive_task = asyncio.create_task(keep_alive())
    
    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            
            if not user_message:
                await websocket.send_json({"type": "error", "content": "Empty message"})
                continue
            
            # Check daily quota before processing (for non-admin)
            if not is_admin:
                allowed, used, remaining = await tracker.check_quota(fingerprint)
                if not allowed:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"You've used your {settings.daily_request_limit} daily queries. Come back tomorrow!"
                    })
                    await websocket.close(code=4003, reason="Daily quota exceeded")
                    return
            
            # Stream response from Claude orchestrator
            turn_completed = False
            try:
                async for chunk in handle_conversation(conversation_id, user_message, agent_config):
                    # Check if connection is still open before sending
                    if websocket.client_state != WebSocketState.CONNECTED:
                        logger.warning(f"WebSocket disconnected during response: {conversation_id}")
                        break
                    await websocket.send_json(chunk)
                
                turn_completed = True
                
                # Increment usage counter and send quota update (non-admin only)
                if not is_admin:
                    new_count = await tracker.increment_usage(
                        fingerprint, 
                        user_agent=user_agent,
                        ip_address=client_ip,
                    )
                    remaining = max(0, settings.daily_request_limit - new_count)
                    logger.info(f"Turn completed for {user_id}...: {new_count}/{settings.daily_request_limit} used, {remaining} remaining")
                    
                    # Send quota update to frontend
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_json({
                            "type": "quota_update",
                            "requests_used": new_count,
                            "requests_remaining": remaining,
                            "daily_limit": settings.daily_request_limit,
                        })
                
                # Signal end of response (if still connected)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "done"})
            except Exception as e:
                logger.error(f"Error during conversation: {e}")
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "error", "content": str(e)})
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {conversation_id}")
    finally:
        keep_alive_task.cancel()
        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass
