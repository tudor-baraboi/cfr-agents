"""
Feedback service for collecting user feedback with logs stored in Azure Blob Storage.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from azure.data.tables.aio import TableServiceClient, TableClient
from azure.storage.blob.aio import BlobServiceClient, ContainerClient
from azure.core.exceptions import ResourceExistsError

from app.config import get_settings

logger = logging.getLogger(__name__)

TABLE_NAME = "Feedback"
BLOB_CONTAINER = "feedback-logs"


class FeedbackService:
    """Service for storing user feedback with logs in Azure storage."""
    
    def __init__(self):
        self._table_client: TableServiceClient | None = None
        self._table: TableClient | None = None
        self._blob_client: BlobServiceClient | None = None
        self._container: ContainerClient | None = None
        self._settings = get_settings()
    
    async def _get_table(self) -> TableClient:
        """Get or create the feedback table client."""
        if self._table is not None:
            return self._table
        
        conn_str = self._settings.azure_blob_connection_string
        self._table_client = TableServiceClient.from_connection_string(conn_str)
        self._table = self._table_client.get_table_client(TABLE_NAME)
        
        # Idempotent table creation
        try:
            await self._table_client.create_table(TABLE_NAME)
            logger.info(f"Created table: {TABLE_NAME}")
        except ResourceExistsError:
            pass  # Table already exists
        except Exception as e:
            logger.debug(f"Table creation note: {e}")
        
        return self._table
    
    async def _get_container(self) -> ContainerClient:
        """Get or create the blob container for logs."""
        if self._container is not None:
            return self._container
        
        conn_str = self._settings.azure_blob_connection_string
        self._blob_client = BlobServiceClient.from_connection_string(conn_str)
        self._container = self._blob_client.get_container_client(BLOB_CONTAINER)
        
        # Idempotent container creation
        try:
            await self._container.create_container()
            logger.info(f"Created blob container: {BLOB_CONTAINER}")
        except ResourceExistsError:
            pass  # Container already exists
        except Exception as e:
            logger.debug(f"Container creation note: {e}")
        
        return self._container
    
    async def submit_feedback(
        self,
        fingerprint: str,
        feedback_type: str,
        message: str,
        logs: list[dict[str, Any]],
        user_agent: str,
        contact: dict[str, str] | None = None,
    ) -> str:
        """
        Submit user feedback with attached logs.
        
        Args:
            fingerprint: User's browser fingerprint
            feedback_type: "bug", "feature", or "other"
            message: User's feedback message
            logs: Array of log entries from frontend
            user_agent: Browser user agent string
            contact: Optional contact info {name, email, phone, company}
        
        Returns:
            Feedback ID (UUID)
        """
        feedback_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        
        # Upload logs to blob storage
        logs_blob_url = await self._upload_logs(feedback_id, date_str, logs, user_agent)
        
        # Store feedback metadata in table
        table = await self._get_table()
        
        entity = {
            "PartitionKey": date_str,
            "RowKey": feedback_id,
            "Type": feedback_type,
            "Message": message[:32000] if message else "",  # Azure Table max string size
            "Fingerprint": fingerprint,
            "LogsBlobUrl": logs_blob_url,
            "UserAgent": user_agent[:1000] if user_agent else "",
            "CreatedAt": now.isoformat(),
        }
        
        # Add optional contact fields
        if contact:
            if contact.get("name"):
                entity["ContactName"] = contact["name"][:500]
            if contact.get("email"):
                entity["ContactEmail"] = contact["email"][:500]
            if contact.get("phone"):
                entity["ContactPhone"] = contact["phone"][:100]
            if contact.get("company"):
                entity["ContactCompany"] = contact["company"][:500]
        
        await table.upsert_entity(entity)
        logger.info(f"Feedback submitted: {feedback_id} (type={feedback_type}, fingerprint={fingerprint[:8]}...)")
        
        return feedback_id
    
    async def _upload_logs(
        self,
        feedback_id: str,
        date_str: str,
        logs: list[dict[str, Any]],
        user_agent: str,
    ) -> str:
        """Upload logs to blob storage and return the blob URL."""
        container = await self._get_container()
        
        blob_name = f"{date_str}/{feedback_id}.json"
        blob_client = container.get_blob_client(blob_name)
        
        import json
        logs_data = {
            "feedbackId": feedback_id,
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
            "userAgent": user_agent,
            "logCount": len(logs),
            "logs": logs,
        }
        
        await blob_client.upload_blob(
            json.dumps(logs_data, indent=2, default=str),
            overwrite=True,
        )
        
        logger.info(f"Uploaded {len(logs)} log entries to blob: {blob_name}")
        return blob_client.url
    
    async def close(self):
        """Clean up connections."""
        if self._table_client:
            await self._table_client.close()
            self._table_client = None
            self._table = None
        if self._blob_client:
            await self._blob_client.close()
            self._blob_client = None
            self._container = None
    
    async def list_all_feedback(self) -> list[dict]:
        """
        List all feedback records.
        Returns records sorted by date descending (newest first).
        """
        table = await self._get_table()
        
        records = []
        async for entity in table.list_entities():
            contact = {}
            if entity.get("ContactName"):
                contact["name"] = entity.get("ContactName")
            if entity.get("ContactEmail"):
                contact["email"] = entity.get("ContactEmail")
            if entity.get("ContactPhone"):
                contact["phone"] = entity.get("ContactPhone")
            if entity.get("ContactCompany"):
                contact["company"] = entity.get("ContactCompany")
            
            records.append({
                "id": entity.get("RowKey", ""),
                "date": entity.get("PartitionKey", ""),
                "type": entity.get("Type", ""),
                "message": entity.get("Message", ""),
                "fingerprint": entity.get("Fingerprint", ""),
                "logs_url": entity.get("LogsBlobUrl", ""),
                "user_agent": entity.get("UserAgent", ""),
                "created_at": entity.get("CreatedAt"),
                "contact": contact if contact else None,
            })
        
        # Sort by created_at descending (newest first)
        records.sort(
            key=lambda r: r["created_at"] or "", 
            reverse=True
        )
        
        return records


# Singleton instance
_service: FeedbackService | None = None


def get_feedback_service() -> FeedbackService:
    """Get the singleton FeedbackService instance."""
    global _service
    if _service is None:
        _service = FeedbackService()
    return _service
