"""
Update Azure AI Search index schema to add personal document fields.

Adds:
- owner_fingerprint: String, Filterable (null = regulatory doc, value = user's fingerprint)
- uploaded_at: DateTimeOffset, Filterable, Sortable (when document was uploaded)
- page_count: Int32 (number of pages in source PDF)
- file_hash: String, Filterable (SHA-256 hash for deduplication)

Usage:
    # Preview changes (no modifications)
    python scripts/update_index_schema.py --dry-run

    # Apply changes to a specific index
    python scripts/update_index_schema.py --index faa-agent

    # Apply changes to all indexes
    python scripts/update_index_schema.py --all

Note: This script only ADDS new fields. Existing documents will have null values
for the new fields, which is correct (regulatory docs have owner_fingerprint = null).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import httpx

# Add backend to path for imports and set working directory for .env loading
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))
os.chdir(backend_path)

from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# New fields to add for personal document support
NEW_FIELDS = [
    {
        "name": "owner_fingerprint",
        "type": "Edm.String",
        "filterable": True,
        "searchable": False,
        "retrievable": True,
        "sortable": False,
        "facetable": False,
    },
    {
        "name": "uploaded_at",
        "type": "Edm.DateTimeOffset",
        "filterable": True,
        "searchable": False,
        "retrievable": True,
        "sortable": True,
        "facetable": False,
    },
    {
        "name": "page_count",
        "type": "Edm.Int32",
        "filterable": False,
        "searchable": False,
        "retrievable": True,
        "sortable": False,
        "facetable": False,
    },
    {
        "name": "file_hash",
        "type": "Edm.String",
        "filterable": True,
        "searchable": False,
        "retrievable": True,
        "sortable": False,
        "facetable": False,
    },
]

ALL_INDEXES = ["faa-agent", "nrc-agent", "dod-agent"]


async def get_index_schema(client: httpx.AsyncClient, endpoint: str, api_key: str, index_name: str) -> dict | None:
    """Fetch current index schema from Azure AI Search."""
    url = f"{endpoint}/indexes/{index_name}?api-version=2024-07-01"
    
    try:
        response = await client.get(
            url,
            headers={"api-key": api_key, "Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.error(f"Index '{index_name}' not found")
        else:
            logger.error(f"Failed to get index schema: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Error fetching index schema: {e}")
        return None


async def update_index_schema(
    client: httpx.AsyncClient, 
    endpoint: str, 
    api_key: str, 
    index_name: str, 
    schema: dict,
    dry_run: bool = False
) -> bool:
    """Update index schema with new fields."""
    url = f"{endpoint}/indexes/{index_name}?api-version=2024-07-01"
    
    if dry_run:
        logger.info(f"[DRY RUN] Would update index '{index_name}' with schema:")
        logger.info(json.dumps(schema, indent=2)[:500] + "...")
        return True
    
    try:
        response = await client.put(
            url,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=schema,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to update index: {e.response.status_code} - {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"Error updating index: {e}")
        return False


async def process_index(
    client: httpx.AsyncClient,
    endpoint: str,
    api_key: str,
    index_name: str,
    dry_run: bool = False
) -> bool:
    """Process a single index: check current schema and add new fields if needed."""
    logger.info(f"\n{'='*50}")
    logger.info(f"Processing index: {index_name}")
    logger.info(f"{'='*50}")
    
    # Get current schema
    schema = await get_index_schema(client, endpoint, api_key, index_name)
    if not schema:
        return False
    
    # Get existing field names
    existing_fields = {f["name"] for f in schema.get("fields", [])}
    logger.info(f"Existing fields ({len(existing_fields)}): {', '.join(sorted(existing_fields))}")
    
    # Check which new fields need to be added
    fields_to_add = []
    for field in NEW_FIELDS:
        if field["name"] in existing_fields:
            logger.info(f"  ✓ Field '{field['name']}' already exists")
        else:
            logger.info(f"  + Field '{field['name']}' will be added")
            fields_to_add.append(field)
    
    if not fields_to_add:
        logger.info(f"No changes needed for index '{index_name}'")
        return True
    
    # Add new fields to schema
    schema["fields"].extend(fields_to_add)
    
    # Remove @odata.context and @odata.etag if present (can't send these back)
    schema.pop("@odata.context", None)
    schema.pop("@odata.etag", None)
    
    # Update the index
    logger.info(f"\nAdding {len(fields_to_add)} new fields to '{index_name}'...")
    
    if await update_index_schema(client, endpoint, api_key, index_name, schema, dry_run):
        if dry_run:
            logger.info(f"[DRY RUN] Would have updated '{index_name}' successfully")
        else:
            logger.info(f"✓ Successfully updated '{index_name}'")
        return True
    else:
        logger.error(f"✗ Failed to update '{index_name}'")
        return False


async def main():
    parser = argparse.ArgumentParser(
        description="Update Azure AI Search index schema for personal document support"
    )
    parser.add_argument(
        "--index", 
        type=str, 
        help="Specific index to update (e.g., faa-agent)"
    )
    parser.add_argument(
        "--all", 
        action="store_true", 
        help="Update all indexes (faa-agent, nrc-agent, dod-agent)"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="Preview changes without making modifications"
    )
    
    args = parser.parse_args()
    
    if not args.index and not args.all:
        parser.error("Must specify --index <name> or --all")
    
    # Load settings
    settings = get_settings()
    
    if not settings.azure_search_endpoint or not settings.azure_search_key:
        logger.error("Azure Search credentials not configured in .env file")
        logger.error("Required: AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY")
        sys.exit(1)
    
    # Determine which indexes to process
    indexes = ALL_INDEXES if args.all else [args.index]
    
    logger.info(f"Azure Search Endpoint: {settings.azure_search_endpoint}")
    logger.info(f"Indexes to process: {', '.join(indexes)}")
    if args.dry_run:
        logger.info("Mode: DRY RUN (no changes will be made)")
    else:
        logger.info("Mode: LIVE (changes will be applied)")
    
    # Process indexes
    async with httpx.AsyncClient(timeout=30.0) as client:
        results = []
        for index_name in indexes:
            success = await process_index(
                client,
                settings.azure_search_endpoint,
                settings.azure_search_key,
                index_name,
                args.dry_run
            )
            results.append((index_name, success))
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("SUMMARY")
    logger.info(f"{'='*50}")
    
    for index_name, success in results:
        status = "✓" if success else "✗"
        logger.info(f"  {status} {index_name}")
    
    success_count = sum(1 for _, s in results if s)
    total = len(results)
    
    if success_count == total:
        logger.info(f"\nAll {total} indexes processed successfully!")
    else:
        logger.error(f"\n{total - success_count}/{total} indexes failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
