"""
Feedback router for collecting user feedback and logs.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.routers.auth import decode_jwt_token
from app.services.feedback import get_feedback_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


class ContactInfo(BaseModel):
    """Optional contact information."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None


class FeedbackRequest(BaseModel):
    """Request body for feedback submission."""
    type: str  # "bug", "feature", or "other"
    message: str
    logs: list[dict[str, Any]] = []
    userAgent: str = ""
    contact: Optional[ContactInfo] = None


class FeedbackResponse(BaseModel):
    """Response for successful feedback submission."""
    id: str
    message: str


async def get_current_user(authorization: Optional[str]) -> dict:
    """Extract user info from JWT token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # Handle "Bearer <token>" format
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization
    
    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return {
        "fingerprint": payload.get("fingerprint", "unknown"),
        "is_admin": payload.get("is_admin", False),
    }


@router.post("/submit", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    authorization: Annotated[Optional[str], Header()] = None,
) -> FeedbackResponse:
    """
    Submit user feedback with attached logs.
    
    Logs are stored in Azure Blob Storage, metadata in Azure Table Storage.
    """
    user = await get_current_user(authorization)
    
    # Validate feedback type
    valid_types = ["bug", "feature", "other"]
    if request.type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid feedback type. Must be one of: {', '.join(valid_types)}"
        )
    
    # Validate message
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    
    # Submit feedback
    service = get_feedback_service()
    
    contact_dict = None
    if request.contact:
        contact_dict = {
            "name": request.contact.name,
            "email": request.contact.email,
            "phone": request.contact.phone,
            "company": request.contact.company,
        }
    
    feedback_id = await service.submit_feedback(
        fingerprint=user["fingerprint"],
        feedback_type=request.type,
        message=request.message.strip(),
        logs=request.logs,
        user_agent=request.userAgent,
        contact=contact_dict,
    )
    
    return FeedbackResponse(
        id=feedback_id,
        message="Thank you for your feedback!",
    )
