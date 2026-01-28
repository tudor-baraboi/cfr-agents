"""
Admin router for viewing usage statistics and feedback.
Protected endpoints for administrators only.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from app.routers.auth import verify_admin_token
from app.services.usage import get_usage_tracker
from app.services.feedback import get_feedback_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/usage")
async def get_all_usage(admin_code: str = Depends(verify_admin_token)) -> dict[str, Any]:
    """
    Get all usage records across all dates.
    
    Returns usage sorted by date descending (newest first).
    Requires admin authorization.
    """
    logger.info(f"Admin {admin_code[:8]}... fetching usage data")
    
    tracker = get_usage_tracker()
    records = await tracker.list_all_usage()
    
    return {"usage": records}


@router.get("/feedback")
async def get_all_feedback(admin_code: str = Depends(verify_admin_token)) -> dict[str, Any]:
    """
    Get all feedback records.
    
    Returns feedback sorted by date descending (newest first).
    Requires admin authorization.
    """
    logger.info(f"Admin {admin_code[:8]}... fetching feedback data")
    
    service = get_feedback_service()
    records = await service.list_all_feedback()
    
    return {"feedback": records}
