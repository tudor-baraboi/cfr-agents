"""
NRC ADAMS Public Search (APS) API tools.

Provides search and document fetching for NRC regulatory documents.
Uses the new ADAMS Public Search API (released Dec 2025) which replaces the deprecated WBA API.

API Documentation: docs/aps-api-documentation.md
Developer Portal: https://adams-api-developer.nrc.gov/
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.services.cache import DocumentCache, get_cache
from app.services.indexer import schedule_indexing

logger = logging.getLogger(__name__)

# Mock mode for testing when ADAMS API key is not available
APS_MOCK_MODE = os.getenv("APS_MOCK_MODE", "false").lower() == "true"

# API base URL
APS_API_BASE_URL = "https://adams-api.nrc.gov/aps/api/search"


def _get_mock_search_results(query: str, doc_type: str | None = None) -> str:
    """Return mock search results for testing."""
    return f"""## NRC ADAMS Search Results (MOCK MODE)

Found 3 documents for: {query}

### 1. Mock Part 21 Report - Safety Valve Defect
**Accession Number:** ML24001A001
**Date:** 2024-01-15
**Type:** Part 21 Correspondence
**Summary:** Mock document for testing - describes a safety valve defect notification.

### 2. Mock Inspection Report - Vogtle Unit 3
**Accession Number:** ML24001A002  
**Date:** 2024-01-10
**Type:** Inspection Report
**Summary:** Mock inspection report for testing purposes.

### 3. Mock NUREG Report - Safety Analysis
**Accession Number:** ML24001A003
**Date:** 2024-01-05
**Type:** NUREG
**Summary:** Mock NUREG report for testing the NRC agent.

---
*Note: These are mock results. Set APS_MOCK_MODE=false and provide APS_API_KEY for real results.*
"""


def _get_mock_document(accession_number: str) -> str:
    """Return mock document content for testing."""
    return f"""## NRC Document: {accession_number} (MOCK MODE)

**Accession Number:** {accession_number}
**Title:** Mock NRC Document for Testing
**Document Date:** 2024-01-15
**Document Type:** Part 21 Correspondence

### Document Content

This is mock content for testing the NRC agent when the ADAMS API key is not configured.

In a real scenario, this would contain the full text of the NRC document, including:
- Regulatory requirements
- Technical specifications  
- Safety analysis
- Compliance guidance

### References
- 10 CFR Part 21 - Reporting of Defects and Noncompliance
- NUREG-0800 - Standard Review Plan
- Regulatory Guide 1.174 - Risk-Informed Decision Making

---
*Note: This is mock content. Set APS_MOCK_MODE=false and provide APS_API_KEY for real documents.*
"""


async def search_aps(
    query: str,
    doc_type: str | None = None,
    max_results: int = 20,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """
    Search NRC ADAMS for documents using the APS API.
    
    Args:
        query: Full-text search query
        doc_type: Optional document type filter (e.g., 'Inspection Report', 'NUREG')
        max_results: Maximum results to return (default 20)
        date_from: Optional start date filter (YYYY-MM-DD format)
        date_to: Optional end date filter (YYYY-MM-DD format)
    
    Returns:
        Formatted search results with accession numbers and titles
    """
    # Check for mock mode
    if APS_MOCK_MODE:
        logger.warning("APS_MOCK_MODE enabled - returning mock results")
        return _get_mock_search_results(query, doc_type)
    
    settings = get_settings()
    api_key = settings.aps_api_key
    
    if not api_key:
        logger.warning("APS_API_KEY not configured - returning mock results")
        return _get_mock_search_results(query, doc_type)
    
    # Build request body
    request_body: dict[str, Any] = {
        "q": query,
        "filters": [],
        "anyFilters": [],
        "legacyLibFilter": False,  # Pre-1999 documents
        "mainLibFilter": True,     # Documents since Nov 1999
        "sort": "DocumentDate",
        "sortDirection": 1,        # 1 = Descending (newest first)
        "skip": 0,
    }
    
    # Add document type filter
    if doc_type:
        request_body["filters"].append({
            "field": "DocumentType",
            "value": doc_type,
            "operator": "contains",
        })
    
    # Add date filters
    if date_from:
        request_body["filters"].append({
            "field": "DocumentDate",
            "value": f"(DocumentDate ge '{date_from}')",
        })
    if date_to:
        request_body["filters"].append({
            "field": "DocumentDate",
            "value": f"(DocumentDate le '{date_to}')",
        })
    
    logger.info(f"Searching APS: query={query}, doc_type={doc_type}")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                APS_API_BASE_URL,
                json=request_body,
                headers={
                    "Ocp-Apim-Subscription-Key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            
            data = response.json()
            # APS API returns results in 'results' array, each with a 'document' sub-object
            raw_results = data.get("results", [])
            total_count = data.get("count", len(raw_results))
            
            if not raw_results:
                return f"No results found for: {query}"
            
            # Format results
            output = [f"## NRC ADAMS Search Results\n"]
            output.append(f"Found {total_count} documents for: {query}\n")
            
            for i, result in enumerate(raw_results[:max_results], 1):
                doc = result.get("document", result)  # Handle both formats
                accession = doc.get("AccessionNumber", "Unknown")
                title = doc.get("DocumentTitle", doc.get("Name", "Untitled"))
                doc_date = doc.get("DocumentDate", doc.get("DateAdded", ""))
                doc_type_result = doc.get("DocumentType", [])
                if isinstance(doc_type_result, list):
                    doc_type_result = ", ".join(doc_type_result) if doc_type_result else ""
                
                output.append(f"\n### {i}. {title}")
                output.append(f"- **Accession Number:** {accession}")
                if doc_type_result:
                    output.append(f"- **Type:** {doc_type_result}")
                if doc_date:
                    output.append(f"- **Date:** {doc_date}")
            
            if total_count > max_results:
                output.append(f"\n*Showing {min(len(raw_results), max_results)} of {total_count} results*")
            
            return "\n".join(output)
            
    except httpx.HTTPStatusError as e:
        logger.error(f"APS search HTTP error: {e}")
        return f"Error searching NRC ADAMS: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error(f"APS search error: {e}")
        return f"Error searching NRC ADAMS: {e}"


async def fetch_aps_document(
    accession_number: str,
    index_name: str | None = None,
) -> str:
    """
    Fetch a specific NRC document by accession number using the APS API.
    
    Args:
        accession_number: ADAMS accession number (e.g., 'ML13095A205')
        index_name: Optional search index name (injected by orchestrator)
    
    Returns:
        Document metadata and content (if available)
    """
    # Check for mock mode
    if APS_MOCK_MODE:
        logger.warning(f"APS_MOCK_MODE enabled - returning mock document for {accession_number}")
        return _get_mock_document(accession_number)
    
    settings = get_settings()
    api_key = settings.aps_api_key
    
    if not api_key:
        logger.warning("APS_API_KEY not configured - returning mock document")
        return _get_mock_document(accession_number)
    
    # Normalize accession number
    accession_number = accession_number.upper().strip()
    
    # Check cache first
    cache_key = DocumentCache.aps_key(accession_number)
    if settings.cache_enabled:
        try:
            cache = get_cache()
            cached = await cache.get(cache_key)
            if cached:
                logger.info(f"APS cache hit: {accession_number}")
                # Auto-index on cache hit if enabled
                if not cached.indexed and settings.auto_index_on_cache_hit:
                    schedule_indexing(
                        content=cached.content,
                        doc_type="aps",
                        doc_id=accession_number,
                        title=cached.title or f"NRC Document {accession_number}",
                        source_url=f"https://adams.nrc.gov/wba/public/doc/{accession_number}",
                        cache_key=cache_key,
                        index_name=index_name,
                    )
                return cached.content
        except Exception as e:
            logger.warning(f"APS cache check failed: {e}")
    
    logger.info(f"Fetching APS document: {accession_number}")
    
    # Use the Get Document endpoint
    url = f"{APS_API_BASE_URL}/{accession_number}"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                url,
                headers={
                    "Ocp-Apim-Subscription-Key": api_key,
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            
            data = response.json()
            doc = data.get("document", data)
            
            if not doc:
                return f"Document not found: {accession_number}"
            
            # Build document content
            title = doc.get("DocumentTitle", doc.get("Name", "Untitled"))
            doc_type = doc.get("DocumentType", [])
            if isinstance(doc_type, list):
                doc_type = ", ".join(doc_type) if doc_type else "Unknown"
            doc_date = doc.get("DocumentDate", "")
            author = doc.get("AuthorName", [])
            if isinstance(author, list):
                author = ", ".join(author)
            author_affil = doc.get("AuthorAffiliation", "")
            keywords = doc.get("Keyword", "")
            docket = doc.get("DocketNumber", "")
            url_link = doc.get("Url", "")
            content = doc.get("content", "")
            page_count = doc.get("EstimatedPageCount", "")
            
            result = [
                f"## {doc_type}: {title}",
                f"**Accession Number:** {accession_number}",
            ]
            
            if doc_date:
                result.append(f"**Document Date:** {doc_date}")
            if author:
                result.append(f"**Author:** {author}")
            if author_affil:
                result.append(f"**Author Affiliation:** {author_affil}")
            if docket:
                result.append(f"**Docket Number:** {docket}")
            if keywords:
                result.append(f"**Keywords:** {keywords}")
            if page_count:
                result.append(f"**Estimated Pages:** {page_count}")
            
            if url_link:
                result.append(f"\n**Document URL:** {url_link}")
            
            # Add document content if available
            if content:
                # Truncate if too long
                if len(content) > 15000:
                    content = content[:15000] + "\n\n[... Document truncated. Full document is larger.]"
                result.append(f"\n### Document Content\n\n{content}")
            else:
                result.append("\n*Document content not included in API response. Use the URL above to access the full document.*")
            
            full_content = "\n".join(result)
            
            # Store in cache
            if settings.cache_enabled:
                try:
                    cache = get_cache()
                    await cache.put(
                        key=cache_key,
                        content=full_content,
                        doc_type="aps",
                        doc_id=accession_number,
                        title=title,
                        metadata={
                            "document_type": doc_type,
                            "document_date": doc_date,
                            "author": author,
                            "docket": docket,
                        },
                    )
                    # Auto-index newly fetched document
                    if settings.auto_index_on_cache_hit:
                        schedule_indexing(
                            content=full_content,
                            doc_type="aps",
                            doc_id=accession_number,
                            title=title,
                            source_url=f"https://adams.nrc.gov/wba/public/doc/{accession_number}",
                            cache_key=cache_key,
                            index_name=index_name,
                        )
                except Exception as e:
                    logger.warning(f"Failed to cache APS document: {e}")
            
            return full_content
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Document not found: {accession_number}"
        logger.error(f"APS fetch HTTP error: {e}")
        return f"Error fetching NRC document: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error(f"APS fetch error: {e}")
        return f"Error fetching NRC document: {e}"


# Tool definitions for Claude API

SEARCH_APS_DEFINITION = {
    "name": "search_aps",
    "description": """Search NRC ADAMS (Agency-wide Documents Access and Management System) for regulatory documents.

**IMPORTANT**: Always use search_indexed_content FIRST before using this tool. Only use search_aps when:
- The index search returned no results or insufficient results
- You need documents that might not be in the index yet
- Looking for very recent documents (last few days)

Use this tool for:
- Looking for NRC inspection reports, NUREG reports, or correspondence
- Searching for nuclear regulatory guidance documents
- Finding documents related to specific dockets, licensees, or facilities

Document types include:
- NUREG reports
- Inspection Reports  
- Correspondence
- Regulatory Guides
- License amendments
- Part 21 Reports

The search uses a full-text query to find relevant documents. Results include accession numbers and titles.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g., 'safety valve Part 21' or 'Vogtle inspection report')",
            },
            "doc_type": {
                "type": "string",
                "description": "Optional document type filter (e.g., 'NUREG', 'Inspection Report', 'Regulatory Guide', 'Part 21')",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 20)",
                "default": 20,
            },
            "date_from": {
                "type": "string",
                "description": "Optional: filter documents from this date (YYYY-MM-DD format)",
            },
            "date_to": {
                "type": "string",
                "description": "Optional: filter documents until this date (YYYY-MM-DD format)",
            },
        },
        "required": ["query"],
    },
}

FETCH_APS_DOCUMENT_DEFINITION = {
    "name": "fetch_aps_document",
    "description": """Fetch a specific NRC document from ADAMS by its accession number.

Use this tool when:
- You have a specific accession number (e.g., 'ML13095A205')
- You found a document in search results and want the full content
- User asks for a specific NRC document

This retrieves document metadata and content from the ADAMS API.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "accession_number": {
                "type": "string",
                "description": "ADAMS accession number (e.g., 'ML13095A205')",
            },
        },
        "required": ["accession_number"],
    },
}
