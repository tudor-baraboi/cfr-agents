#!/usr/bin/env python3
"""
Check daily usage quotas from Azure Table Storage.

Usage:
    python scripts/check_daily_usage.py
    python scripts/check_daily_usage.py --date 2026-01-24
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv

# Load .env from backend
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")


async def check_usage(target_date: str | None = None):
    """Check usage for a specific date (defaults to today)."""
    from azure.data.tables.aio import TableServiceClient
    
    conn_str = os.getenv("AZURE_BLOB_CONNECTION_STRING")
    if not conn_str:
        print("Error: AZURE_BLOB_CONNECTION_STRING not set in backend/.env")
        return
    
    # Use today if no date specified
    if target_date is None:
        target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    print(f"\n=== Daily Usage for {target_date} ===\n")
    
    async with TableServiceClient.from_connection_string(conn_str) as client:
        table = client.get_table_client("DailyUsage")
        
        try:
            # Query all entities for the target date (partition)
            entities = []
            async for entity in table.query_entities(f"PartitionKey eq '{target_date}'"):
                entities.append(entity)
            
            if not entities:
                print("No usage records found for this date.")
                return
            
            # Sort by request count descending
            entities.sort(key=lambda x: x.get("RequestCount", 0), reverse=True)
            
            print(f"{'Fingerprint':<20} {'Requests':<10} {'First Request':<25} {'Last Request':<25}")
            print("-" * 80)
            
            total_requests = 0
            for entity in entities:
                fingerprint = entity.get("RowKey", "unknown")[:16] + "..."
                count = entity.get("RequestCount", 0)
                first = entity.get("FirstRequestAt", "")
                last = entity.get("LastRequestAt", "")
                
                # Format timestamps
                if hasattr(first, 'strftime'):
                    first = first.strftime("%Y-%m-%d %H:%M:%S")
                if hasattr(last, 'strftime'):
                    last = last.strftime("%Y-%m-%d %H:%M:%S")
                
                print(f"{fingerprint:<20} {count:<10} {str(first):<25} {str(last):<25}")
                total_requests += count
            
            print("-" * 80)
            print(f"Total: {len(entities)} unique visitors, {total_requests} total requests")
            
        except Exception as e:
            if "TableNotFound" in str(e):
                print("DailyUsage table does not exist yet. No usage recorded.")
            else:
                print(f"Error querying table: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Check daily usage quotas")
    parser.add_argument("--date", help="Date to check (YYYY-MM-DD), defaults to today")
    args = parser.parse_args()
    
    asyncio.run(check_usage(args.date))
