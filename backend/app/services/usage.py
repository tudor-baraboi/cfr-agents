"""
Daily usage quota tracking with Azure Table Storage.

Uses FingerprintJS visitor IDs as rate limit keys.
Quotas reset daily (partition by date).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from azure.data.tables.aio import TableServiceClient, TableClient
from azure.core.exceptions import ResourceNotFoundError

from app.config import get_settings

logger = logging.getLogger(__name__)

TABLE_NAME = "DailyUsage"


class UsageTracker:
    """
    Async usage quota tracker backed by Azure Table Storage.
    
    Storage layout:
        DailyUsage table:
            PartitionKey: date (YYYY-MM-DD)
            RowKey: fingerprint_id
    """
    
    def __init__(self):
        self._client: TableServiceClient | None = None
        self._table: TableClient | None = None
        self._settings = get_settings()
    
    async def _get_table(self) -> TableClient:
        """Get or create the table client."""
        if self._table is not None:
            return self._table
        
        conn_str = self._settings.azure_blob_connection_string
        if not conn_str:
            raise ValueError("Azure Storage connection string not configured")
        
        self._client = TableServiceClient.from_connection_string(conn_str)
        self._table = self._client.get_table_client(TABLE_NAME)
        
        # Ensure table exists (idempotent)
        try:
            await self._client.create_table(TABLE_NAME)
            logger.info(f"Created table: {TABLE_NAME}")
        except Exception:
            pass  # Table already exists
        
        return self._table
    
    async def close(self):
        """Close the table service client."""
        if self._client:
            await self._client.close()
            self._client = None
            self._table = None
    
    @staticmethod
    def _today_partition() -> str:
        """Get today's date as partition key (UTC)."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    async def get_usage(self, fingerprint: str) -> int:
        """Get today's request count for a fingerprint. Returns 0 if not found."""
        table = await self._get_table()
        partition = self._today_partition()
        
        try:
            entity = await table.get_entity(
                partition_key=partition,
                row_key=fingerprint
            )
            return entity.get("RequestCount", 0)
        except ResourceNotFoundError:
            return 0
        except Exception as e:
            logger.error(f"Failed to get usage for {fingerprint[:8]}...: {e}")
            return 0
    
    async def increment_usage(
        self, 
        fingerprint: str, 
        user_agent: str = "",
        ip_address: str | None = None,
    ) -> int:
        """
        Increment today's request count for a fingerprint.
        Creates record if it doesn't exist.
        Optionally tracks IP address and geographic location.
        Returns the new count.
        """
        from app.services.geolocation import get_location_from_ip
        
        table = await self._get_table()
        partition = self._today_partition()
        now = datetime.now(timezone.utc)
        
        # Get location from IP if provided
        location = {}
        if ip_address:
            location = await get_location_from_ip(ip_address)
        
        try:
            # Try to get existing entity
            entity = await table.get_entity(
                partition_key=partition,
                row_key=fingerprint
            )
            entity["RequestCount"] = entity.get("RequestCount", 0) + 1
            entity["LastRequestAt"] = now
            # Update IP/location if we have it and it's not already set
            if ip_address and not entity.get("IPAddress"):
                entity["IPAddress"] = ip_address
                if location:
                    entity["Country"] = location.get("country", "")
                    entity["City"] = location.get("city", "")
            await table.update_entity(entity, mode="merge")
            new_count = entity["RequestCount"]
            
        except ResourceNotFoundError:
            # Create new entity
            entity = {
                "PartitionKey": partition,
                "RowKey": fingerprint,
                "RequestCount": 1,
                "FirstRequestAt": now,
                "LastRequestAt": now,
                "UserAgent": user_agent[:500] if user_agent else "",
            }
            if ip_address:
                entity["IPAddress"] = ip_address
                if location:
                    entity["Country"] = location.get("country", "")
                    entity["City"] = location.get("city", "")
            await table.create_entity(entity)
            new_count = 1
        
        logger.info(f"Fingerprint {fingerprint[:8]}... daily usage: {new_count}")
        return new_count
    
    async def get_remaining(self, fingerprint: str, limit: int | None = None) -> tuple[int, int]:
        """
        Get usage stats for a fingerprint.
        Returns (requests_used, requests_remaining).
        """
        if limit is None:
            limit = self._settings.daily_request_limit
        
        used = await self.get_usage(fingerprint)
        remaining = max(0, limit - used)
        return (used, remaining)
    
    async def check_quota(self, fingerprint: str, limit: int | None = None) -> tuple[bool, int, int]:
        """
        Check if fingerprint is within daily quota.
        Returns (allowed: bool, requests_used: int, requests_remaining: int).
        """
        if limit is None:
            limit = self._settings.daily_request_limit
        
        used = await self.get_usage(fingerprint)
        remaining = max(0, limit - used)
        allowed = used < limit
        return (allowed, used, remaining)
    
    async def list_all_usage(self) -> list[dict]:
        """
        List all usage records across all dates.
        Returns records sorted by date descending (newest first).
        """
        table = await self._get_table()
        
        records = []
        async for entity in table.list_entities():
            records.append({
                "date": entity.get("PartitionKey", ""),
                "fingerprint": entity.get("RowKey", ""),
                "request_count": entity.get("RequestCount", 0),
                "first_request_at": entity.get("FirstRequestAt"),
                "last_request_at": entity.get("LastRequestAt"),
                "user_agent": entity.get("UserAgent", ""),
                "ip_address": entity.get("IPAddress", ""),
                "country": entity.get("Country", ""),
                "city": entity.get("City", ""),
            })
        
        # Sort by date descending, then by last_request_at descending
        records.sort(
            key=lambda r: (r["date"], r["last_request_at"] or ""), 
            reverse=True
        )
        
        return records


# Module-level singleton
_tracker: UsageTracker | None = None


def get_usage_tracker() -> UsageTracker:
    """Get the usage tracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker
