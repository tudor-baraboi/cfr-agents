"""
Authentication router for fingerprint-based daily quotas and admin access codes.
Handles fingerprint validation, JWT issuance, and admin authentication.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from jose import jwt, JWTError

from app.config import get_settings
from app.services.usage import get_usage_tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# JWT settings
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 1  # Fingerprint tokens expire daily (quota resets)


class ValidateCodeRequest(BaseModel):
    code: str
    fingerprint: Optional[str] = None  # Optional fingerprint for My Documents feature


class ValidateCodeResponse(BaseModel):
    token: str
    is_admin: bool
    requests_used: int
    requests_remaining: Optional[int]  # None for admin (unlimited)


class FingerprintRequest(BaseModel):
    visitor_id: str


class FingerprintResponse(BaseModel):
    token: str
    is_admin: bool
    requests_used: int
    requests_remaining: int
    daily_limit: int


def get_admin_codes() -> set[str]:
    """Get set of admin codes from environment."""
    settings = get_settings()
    if not settings.admin_codes:
        return set()
    return set(code.strip() for code in settings.admin_codes.split(",") if code.strip())


def create_jwt_token_for_fingerprint(fingerprint: str) -> str:
    """Create a JWT token for a fingerprint-based user."""
    settings = get_settings()
    payload = {
        "fingerprint": fingerprint,
        "is_admin": False,
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def create_jwt_token_for_admin(code: str, fingerprint: Optional[str] = None) -> str:
    """Create a JWT token for an admin user."""
    settings = get_settings()
    payload = {
        "code": code,
        "is_admin": True,
        "exp": datetime.utcnow() + timedelta(days=30),  # Admin tokens last longer
        "iat": datetime.utcnow(),
    }
    # Include fingerprint if provided (enables My Documents feature for admin)
    if fingerprint:
        payload["fingerprint"] = fingerprint
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns None if invalid."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None


@router.post("/fingerprint", response_model=FingerprintResponse)
async def authenticate_fingerprint(request: FingerprintRequest):
    """
    Authenticate a user by their browser fingerprint.
    
    - Each fingerprint gets a daily quota of requests
    - Quota resets at midnight UTC
    - Returns current usage stats
    """
    visitor_id = request.visitor_id.strip()
    
    if not visitor_id or len(visitor_id) < 10:
        raise HTTPException(status_code=400, detail="Invalid visitor ID")
    
    settings = get_settings()
    tracker = get_usage_tracker()
    
    # Get current usage
    allowed, used, remaining = await tracker.check_quota(visitor_id)
    
    if not allowed:
        logger.info(f"Quota exhausted for fingerprint {visitor_id[:8]}...")
        raise HTTPException(
            status_code=403,
            detail=f"Daily quota exhausted ({used}/{settings.daily_request_limit}). Come back tomorrow!"
        )
    
    # Issue token
    token = create_jwt_token_for_fingerprint(visitor_id)
    logger.info(f"Fingerprint authenticated: {visitor_id[:8]}... ({used}/{settings.daily_request_limit} used)")
    
    return FingerprintResponse(
        token=token,
        is_admin=False,
        requests_used=used,
        requests_remaining=remaining,
        daily_limit=settings.daily_request_limit,
    )


@router.post("/validate-code", response_model=ValidateCodeResponse)
async def validate_code(request: ValidateCodeRequest):
    """
    Validate an admin access code and return a JWT token.
    
    - Admin codes get unlimited access
    - This endpoint is for admin login via ?admin=ADMIN-TUDOR URL param
    """
    code = request.code.strip().upper()
    
    admin_codes = get_admin_codes()
    
    # Check if it's an admin code
    if code in admin_codes:
        logger.info(f"Admin code validated: {code[:8]}... (fingerprint={request.fingerprint[:8] if request.fingerprint else 'none'})")
        token = create_jwt_token_for_admin(code, request.fingerprint)
        return ValidateCodeResponse(
            token=token,
            is_admin=True,
            requests_used=0,
            requests_remaining=None,
        )
    
    # Not an admin code
    logger.warning(f"Invalid admin code attempted: {code[:8]}...")
    raise HTTPException(status_code=401, detail="Invalid access code")


async def verify_admin_token(authorization: Annotated[Optional[str], Header()] = None) -> str:
    """Dependency to verify admin authorization for protected endpoints."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # Accept "Bearer <token>" format
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization
    
    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    if not payload.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return payload["code"]
