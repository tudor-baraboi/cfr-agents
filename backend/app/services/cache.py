"""
Document cache using Azure Blob Storage.

Provides async cache operations for CFR and DRS documents.
Caching reduces API calls and enables progressive indexing.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from azure.storage.blob.aio import BlobServiceClient, ContainerClient
from azure.core.exceptions import ResourceNotFoundError

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class CachedDocument:
    """Cached document with metadata."""
    content: str
    doc_type: str  # "cfr" or "drs"
    doc_id: str
    title: str
    cached_at: str
    hit_count: int
    indexed: bool
    metadata: dict[str, Any]


class DocumentCache:
    """
    Async document cache backed by Azure Blob Storage.
    
    Storage layout:
        documents/
            cfr/
                14-25-1309.json
                14-21-15.json
            drs/
                AC-25.1309-1A.json
                AC-23-8C.json
    
    Each cached document is stored as JSON with content + metadata.
    """
    
    def __init__(self):
        self._client: BlobServiceClient | None = None
        self._container: ContainerClient | None = None
        self._settings = get_settings()
    
    async def _get_container(self) -> ContainerClient:
        """Get or create the blob container client."""
        if self._container is not None:
            return self._container
        
        if not self._settings.azure_blob_connection_string:
            raise ValueError("Azure Blob connection string not configured")
        
        self._client = BlobServiceClient.from_connection_string(
            self._settings.azure_blob_connection_string
        )
        self._container = self._client.get_container_client(
            self._settings.azure_blob_container_name
        )
        
        return self._container
    
    async def close(self):
        """Close the blob service client."""
        if self._client:
            await self._client.close()
            self._client = None
            self._container = None
    
    # Key generation helpers
    
    @staticmethod
    def cfr_key(title: int, part: int, section: str) -> str:
        """Generate cache key for CFR section."""
        # Normalize section (remove subsection refs)
        section_base = section.split("(")[0].strip()
        return f"cfr/{title}-{part}-{section_base}.json"
    
    @staticmethod
    def drs_key(doc_type: str, doc_number: str) -> str:
        """Generate cache key for DRS document."""
        # Normalize doc number (replace spaces, special chars)
        normalized = doc_number.upper().strip()
        normalized = normalized.replace(" ", "-").replace("/", "-")
        return f"drs/{doc_type}-{normalized}.json"
    
    @staticmethod
    def aps_key(accession_number: str) -> str:
        """Generate cache key for NRC ADAMS APS document."""
        # Accession numbers are like ML13095A205 - already normalized
        normalized = accession_number.upper().strip()
        return f"aps/{normalized}.json"
    
    # Cache operations
    
    async def get(self, key: str) -> CachedDocument | None:
        """
        Get document from cache.
        
        Returns None if not found. Increments hit count.
        """
        container = await self._get_container()
        blob = container.get_blob_client(key)
        
        try:
            download = await blob.download_blob()
            data = json.loads(await download.readall())
            
            # Increment hit count
            data["hit_count"] = data.get("hit_count", 0) + 1
            
            # Update in background (don't await - fire and forget)
            try:
                await blob.upload_blob(
                    json.dumps(data),
                    overwrite=True,
                )
            except Exception as e:
                logger.warning(f"Failed to update hit count for {key}: {e}")
            
            logger.info(f"Cache hit: {key} (hits: {data['hit_count']})")
            
            return CachedDocument(
                content=data["content"],
                doc_type=data["doc_type"],
                doc_id=data["doc_id"],
                title=data.get("title", ""),
                cached_at=data.get("cached_at", ""),
                hit_count=data["hit_count"],
                indexed=data.get("indexed", False),
                metadata=data.get("metadata", {}),
            )
            
        except ResourceNotFoundError:
            logger.debug(f"Cache miss: {key}")
            return None
        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            return None
    
    async def put(
        self,
        key: str,
        content: str,
        doc_type: str,
        doc_id: str,
        title: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Store document in cache.
        
        Returns True if successful.
        """
        container = await self._get_container()
        blob = container.get_blob_client(key)
        
        data = {
            "content": content,
            "doc_type": doc_type,
            "doc_id": doc_id,
            "title": title,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "hit_count": 0,
            "indexed": False,
            "metadata": metadata or {},
        }
        
        try:
            await blob.upload_blob(
                json.dumps(data),
                overwrite=True,
            )
            logger.info(f"Cached document: {key}")
            return True
        except Exception as e:
            logger.error(f"Cache put error for {key}: {e}")
            return False
    
    async def mark_indexed(self, key: str) -> bool:
        """Mark a cached document as indexed."""
        container = await self._get_container()
        blob = container.get_blob_client(key)
        
        try:
            download = await blob.download_blob()
            data = json.loads(await download.readall())
            data["indexed"] = True
            data["indexed_at"] = datetime.now(timezone.utc).isoformat()
            
            await blob.upload_blob(
                json.dumps(data),
                overwrite=True,
            )
            logger.info(f"Marked as indexed: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to mark indexed for {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if document exists in cache."""
        container = await self._get_container()
        blob = container.get_blob_client(key)
        return await blob.exists()


# Module-level singleton
_cache: DocumentCache | None = None


def get_cache() -> DocumentCache:
    """Get the document cache singleton."""
    global _cache
    if _cache is None:
        _cache = DocumentCache()
    return _cache
