"""
Fetch CFR sections from the eCFR API.

eCFR API: https://www.ecfr.gov/api/versioner/v1
FAA regulations are in Title 14 (Aeronautics and Space).

Implements cache-first pattern:
1. Check blob storage cache
2. If cached: return content, schedule background indexing (on first hit)
3. If not cached: fetch from API, store in cache, return content
"""

import logging
import re

import httpx

from app.config import get_settings
from app.services.cache import get_cache, DocumentCache
from app.services.indexer import schedule_indexing

logger = logging.getLogger(__name__)


async def fetch_cfr_section(
    part: int,
    section: str,
    title: int = 14,
    date: str | None = None,
    index_name: str | None = None,
) -> str:
    """
    Fetch a CFR section from the eCFR API.
    
    Uses cache-first pattern:
    1. Check blob cache for existing content
    2. On cache hit: return content + schedule indexing if not already indexed
    3. On cache miss: fetch from eCFR, cache the result, return content
    
    Args:
        part: Part number (e.g., 25 for Airworthiness Standards)
        section: Section number (e.g., "1309" or "1309(a)")
        title: CFR title number (14 for FAA) - defaults to 14
        date: Date for version (defaults to latest available, or "YYYY-MM-DD")
    
    Returns:
        Section text content or error message.
    
    Example:
        fetch_cfr_section(25, "1309") -> Returns §25.1309 text
    """
    settings = get_settings()
    
    # Clean section number (remove subsection references for API call)
    section_base = re.split(r'[(\[]', section)[0].strip()
    
    # Generate cache key
    cache_key = DocumentCache.cfr_key(title, part, section_base)
    doc_id = f"{title}-{part}-{section_base}"
    
    # Check cache first (if enabled)
    if settings.cache_enabled:
        try:
            cache = get_cache()
            cached = await cache.get(cache_key)
            
            if cached:
                logger.info(f"Cache hit for CFR {title}/{part}/{section_base}")
                
                # Schedule indexing on first cache hit (not already indexed)
                if not cached.indexed and settings.auto_index_on_cache_hit:
                    schedule_indexing(
                        content=cached.content,
                        doc_type="cfr",
                        doc_id=doc_id,
                        title=cached.title or f"{title} CFR §{part}.{section_base}",
                        source_url=f"https://www.ecfr.gov/current/title-{title}/chapter-I/subchapter-C/part-{part}/section-{part}.{section_base}",
                        cache_key=cache_key,
                        index_name=index_name,
                    )
                
                return cached.content
        except Exception as e:
            logger.warning(f"Cache lookup failed, falling back to API: {e}")
    
    # Cache miss - fetch from API
    base_url = settings.ecfr_api_base_url
    
    # Get the latest available date if not specified
    if not date:
        date = await _get_latest_date(title)
        if not date:
            return f"Error: Could not determine latest date for Title {title}"
    
    # Build the API URL with query params (correct eCFR API format)
    url = f"{base_url}/full/{date}/title-{title}.xml"
    params = {"part": part, "section": f"{part}.{section_base}"}
    
    logger.info(f"Fetching CFR: Title {title}, Part {part}, Section {section_base}")
    logger.debug(f"eCFR URL: {url} with params {params}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            
            if response.status_code == 404:
                return f"Section not found: {title} CFR {part}.{section_base}"
            
            response.raise_for_status()
            
            # Parse XML and extract text content
            content = _extract_text_from_xml(response.text)
            
            # Add citation header
            doc_title = f"{title} CFR §{part}.{section_base}"
            citation = f"## {doc_title}\n\n"
            full_content = citation + content
            
            # Store in cache (if enabled)
            if settings.cache_enabled:
                try:
                    cache = get_cache()
                    await cache.put(
                        key=cache_key,
                        content=full_content,
                        doc_type="cfr",
                        doc_id=doc_id,
                        title=doc_title,
                        metadata={
                            "title": title,
                            "part": part,
                            "section": section_base,
                            "date": date,
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to cache CFR section: {e}")
            
            return full_content
            
        except httpx.TimeoutException:
            logger.error(f"Timeout fetching CFR section: {url}")
            return f"Error: Timeout fetching {title} CFR {part}.{section_base}"
        
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching CFR: {e}")
            return f"Error fetching {title} CFR {part}.{section_base}: HTTP {e.response.status_code}"
        
        except Exception as e:
            logger.error(f"Error fetching CFR section: {e}")
            return f"Error fetching {title} CFR {part}.{section_base}: {e}"


async def _get_latest_date(title: int) -> str | None:
    """Get the latest available date for a CFR title."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get("https://www.ecfr.gov/api/versioner/v1/titles.json")
            response.raise_for_status()
            titles = response.json()
            for t in titles.get("titles", []):
                if t.get("number") == title:
                    return t.get("latest_issue_date")
        except Exception as e:
            logger.error(f"Error getting latest date: {e}")
    return None


def _extract_text_from_xml(xml_content: str) -> str:
    """
    Extract readable text from eCFR XML response.
    
    This is a simple extraction - could be enhanced with proper XML parsing
    if we need structured data.
    """
    import re
    
    # Remove XML tags but preserve structure
    text = xml_content
    
    # Replace paragraph tags with newlines
    text = re.sub(r'<P[^>]*>', '\n', text)
    text = re.sub(r'</P>', '', text)
    
    # Replace heading tags
    text = re.sub(r'<HD[^>]*SOURCE="HD1"[^>]*>([^<]+)</HD>', r'\n### \1\n', text)
    text = re.sub(r'<HD[^>]*>([^<]+)</HD>', r'\n**\1**\n', text)
    
    # Handle subsection references
    text = re.sub(r'<SECTNO>([^<]+)</SECTNO>', r'**\1**', text)
    text = re.sub(r'<SUBJECT>([^<]+)</SUBJECT>', r'*\1*\n', text)
    
    # Remove remaining XML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Clean up whitespace
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    text = text.strip()
    
    # Decode HTML entities
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    
    return text


# Tool definition for Claude API
TOOL_DEFINITION = {
    "name": "fetch_cfr_section",
    "description": """Fetch the complete text of a Code of Federal Regulations (CFR) section from the official eCFR API.

Use this tool when:
- User asks for the text of a specific CFR section
- You need the complete regulatory text (not just a summary)
- You want to verify the exact wording of a regulation

FAA regulations are in Title 14. Common parts:
- Part 21: Certification procedures
- Part 23: Normal category airplanes
- Part 25: Transport category airplanes
- Part 27: Normal category rotorcraft
- Part 29: Transport category rotorcraft
- Part 33: Aircraft engines
- Part 35: Propellers

Example: To get §25.1309, use title=14, part=25, section="1309"
""",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "integer",
                "description": "CFR title number. Use 14 for FAA regulations.",
                "default": 14,
            },
            "part": {
                "type": "integer",
                "description": "CFR part number (e.g., 25 for transport aircraft airworthiness)",
            },
            "section": {
                "type": "string",
                "description": "Section number (e.g., '1309' or '1309' for §25.1309)",
            },
        },
        "required": ["part", "section"],
    },
}
