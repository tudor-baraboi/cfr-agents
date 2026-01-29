"""
IP geolocation service using ip-api.com (free, no API key required).

Rate limit: 45 requests/minute on free tier.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ip-api.com free endpoint (HTTP only on free tier, but returns JSON)
GEOIP_API_URL = "http://ip-api.com/json/{ip}?fields=status,country,city"

# Simple in-memory cache to avoid repeated lookups
_location_cache: dict[str, dict[str, str]] = {}


async def get_location_from_ip(ip: str) -> dict[str, str]:
    """
    Get geographic location from IP address.
    
    Returns dict with 'country' and 'city' keys, or empty dict on failure.
    Results are cached in memory.
    
    Args:
        ip: IP address to look up (IPv4 or IPv6), may include port
    
    Returns:
        {"country": "United States", "city": "New York"} or {}
    """
    if not ip or ip in ("127.0.0.1", "localhost", "::1"):
        return {}
    
    # Strip port if present (e.g., "192.168.1.1:12345" -> "192.168.1.1")
    ip_only = ip.split(":")[0] if ":" in ip and not ip.startswith("[") else ip
    # Handle IPv6 with port: [::1]:8080 -> ::1
    if ip.startswith("[") and "]:" in ip:
        ip_only = ip[1:ip.index("]")]
    
    # Check cache first
    if ip_only in _location_cache:
        return _location_cache[ip_only]
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(GEOIP_API_URL.format(ip=ip_only))
            
            if response.status_code != 200:
                logger.warning(f"Geolocation API returned {response.status_code} for IP {ip}")
                return {}
            
            data = response.json()
            
            if data.get("status") != "success":
                logger.debug(f"Geolocation lookup failed for IP {ip_only}: {data}")
                return {}
            
            result = {
                "country": data.get("country", ""),
                "city": data.get("city", ""),
            }
            
            # Cache the result using cleaned IP
            _location_cache[ip_only] = result
            logger.debug(f"Geolocation for {ip_only}: {result}")
            
            return result
            
    except httpx.TimeoutException:
        logger.warning(f"Geolocation timeout for IP {ip_only}")
        return {}
    except Exception as e:
        logger.warning(f"Geolocation error for IP {ip_only}: {e}")
        return {}


def extract_client_ip(forwarded_for: str | None, remote_addr: str | None) -> str | None:
    """
    Extract the client IP from request headers.
    
    Azure App Service sets X-Forwarded-For header with the client IP.
    Format: "client_ip, proxy1_ip, proxy2_ip"
    
    Args:
        forwarded_for: X-Forwarded-For header value
        remote_addr: Direct remote address (fallback)
    
    Returns:
        Client IP address or None
    """
    if forwarded_for:
        # Take the first IP (original client)
        return forwarded_for.split(",")[0].strip()
    
    return remote_addr
