# Progressive Caching & Indexing System

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Document Request Flow                        │
└─────────────────────────────────────────────────────────────────┘

Claude calls fetch_cfr_section() or fetch_drs_document()
                         │
                         ▼
              ┌─────────────────────┐
              │  Check Blob Cache   │
              │  (Azure Storage)    │
              └─────────────────────┘
                    │         │
           ┌────────┘         └────────┐
           ▼                           ▼
      CACHE HIT                   CACHE MISS
           │                           │
           ▼                           ▼
   Return content              Fetch from API
   immediately                 (eCFR or DRS)
           │                           │
           ▼                           ▼
   If not indexed:             Store in cache
   schedule_indexing()         (hit_count=0)
           │                           │
           ▼                           ▼
   Background task:            Return content
   • Generate embedding
   • Upload to AI Search
   • Mark as indexed
```

## Key Components

| File | Purpose |
|------|---------|
| `backend/app/services/cache.py` | Blob storage wrapper - `get()`, `put()`, `mark_indexed()` |
| `backend/app/services/indexer.py` | Embedding generation + search index upload |
| `backend/app/tools/fetch_cfr.py` | CFR fetching with cache-first pattern |
| `backend/app/tools/drs.py` | DRS fetching with cache-first pattern |

## Cache Storage Layout

```
Azure Blob: faaagentcache/documents/
├── cfr/
│   ├── 14-25-1309.json    # {content, hit_count, indexed, cached_at, ...}
│   └── 14-21-15.json
└── drs/
    ├── AC-25.1309-1A.json
    └── AC-23-8C.json
```

Each cached document is stored as JSON with metadata:

```json
{
  "content": "## 14 CFR §25.1309\n\n...",
  "doc_type": "cfr",
  "doc_id": "14-25-1309",
  "title": "14 CFR §25.1309",
  "cached_at": "2026-01-09T01:06:04+00:00",
  "hit_count": 3,
  "indexed": true,
  "indexed_at": "2026-01-09T01:06:05+00:00",
  "metadata": {
    "title": 14,
    "part": 25,
    "section": "1309"
  }
}
```

## Self-Improving Behavior

1. **First request** → API call → cached (not indexed)
2. **Second request** → cache hit → triggers background indexing
3. **Future requests** → both cached AND searchable via vector search

This means frequently-requested documents automatically migrate into the search index, improving semantic search results over time without manual intervention.

## Background Indexing

Background indexing uses `asyncio.create_task()` for fire-and-forget execution:

```python
def schedule_indexing(...) -> asyncio.Task:
    async def _index_task():
        await index_document(...)  # Generates embedding + uploads to search
    
    return asyncio.create_task(_index_task())  # Runs in background
```

**Characteristics:**
- Simple, no external dependencies
- Works within the existing FastAPI event loop
- Task is lost if server restarts mid-indexing (acceptable for this use case)

## Configuration

Environment variables in `.env`:

```env
# Azure Blob Storage (document cache)
AZURE_BLOB_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_BLOB_CONTAINER_NAME=documents

# Feature flags
CACHE_ENABLED=true              # Enable/disable caching
AUTO_INDEX_ON_CACHE_HIT=true    # Enable/disable auto-indexing
```

## Azure Resources

| Resource | Name | Purpose |
|----------|------|---------|
| Storage Account | `faaagentcache` | Document cache |
| Container | `documents` | Blob container for cached docs |
| AI Search | `faa-ai-search` | Vector search index |
| AI Services | `faa-ai-services` | Cohere embeddings |
