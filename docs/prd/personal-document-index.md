# Personal Document Index (BYOD) PRD

**Version:** 1.0  
**Date:** January 27, 2026  
**Status:** Draft

---

## Overview

Enable users to upload their own PDF documents (internal procedures, company manuals, proprietary guidance) to be indexed and searchable alongside regulatory content. Documents are isolated per user via browser fingerprint filtering, enforced architecturally through a dedicated search service.

---

## Goals

1. **Personal Document Storage**: Users can upload PDFs that get indexed for semantic search
2. **Privacy Isolation**: Documents are only searchable by the user who uploaded them
3. **Seamless Integration**: Personal documents appear in search results alongside regulatory content
4. **Security by Architecture**: Fingerprint filtering enforced at infrastructure level, not application level
5. **OCR Support**: Extract text from scanned PDFs using optical character recognition

---

## Non-Goals (for this version)

- Multi-format support (Word, Excel, etc.) - PDF only
- Shared documents between users
- Document versioning
- Folder organization

---

## Architecture

### Current State
```
Frontend → e-cfr-agent-backend (has Azure AI Search credentials) → Azure AI Search
```

### Target State
```
Frontend → e-cfr-agent-backend (NO Azure credentials) → e-cfr-search-proxy (enforces fingerprint) → Azure AI Search
```

### Key Principle
The search proxy is the **only** component with Azure AI Search credentials. It enforces fingerprint filtering on every request. The backend cannot bypass this filter because it has no direct access to Azure AI Search.

---

## New Azure Resources

All resources will be created in a new resource group: `e-cfr-rg`

### Compute & Application

| Resource | Type | Purpose |
|----------|------|---------|
| `e-cfr-agent-backend` | App Service | Main backend (migrated from `faa-agent-backend`) |
| `e-cfr-search-proxy` | App Service | Search proxy with fingerprint enforcement |
| `e-cfr-app-service-plan` | App Service Plan | Hosting plan for App Services (B1 or higher) |

### Data & Search

| Resource | Type | Purpose |
|----------|------|---------|
| `e-cfr-ai-search-service` | Azure AI Search | Managed search service (Basic tier, migrated from `faa-agent-ai-search`) |
| `ecfrstorage` | Storage Account | Blob storage for document cache and logs |
| `e-cfr-postgres` | Azure Database for PostgreSQL | User data, usage tracking, feedback (Flexible Server) |

### AI Services

| Resource | Type | Purpose |
|----------|------|---------|
| `e-cfr-ai-services` | Azure AI Services | Cohere embeddings endpoint |

### Monitoring & Operations

| Resource | Type | Purpose |
|----------|------|---------|
| `e-cfr-app-insights` | Application Insights | APM, logging, performance monitoring |
| `e-cfr-log-analytics` | Log Analytics Workspace | Centralized log storage (required by App Insights) |

### Storage Account Containers

| Container | Purpose |
|-----------|---------|
| `documents` | Cached CFR/DRS documents (fetched regulatory content) |
| `logs` | Conversation logs and feedback data |
| `uploads` | Temporary storage for uploaded PDFs during processing (optional) |

---

## Index Schema Changes

Add to existing indexes (`faa-index`, `nrc-index`, `dod-index`):

| Field | Type | Purpose |
|-------|------|---------|
| `owner_fingerprint` | String, Filterable | `null` = regulatory doc, value = user's fingerprint |
| `uploaded_at` | DateTimeOffset, Filterable | When document was uploaded |
| `page_count` | Int32 | Number of pages in source PDF |
| `file_hash` | String, Filterable | SHA-256 hash for deduplication |

---

## Tool Modifications

### Modified Tools

#### `search_indexed_content` (all agents)

**Current:** Directly calls Azure AI Search SDK with query and filters.

**Change:** Call `e-cfr-search-proxy` instead. The proxy handles:
- Adding fingerprint to request
- Enforcing fingerprint filter
- Returning results

**Implementation:**
```python
# Before
async def search_indexed_content(query: str, index: str, top: int = 5):
    search_client = SearchClient(endpoint, index, credential)
    results = search_client.search(query, top=top)
    return results

# After
async def search_indexed_content(query: str, index: str, fingerprint: str, top: int = 5):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SEARCH_PROXY_URL}/search",
            json={"query": query, "index": index, "fingerprint": fingerprint, "top": top}
        )
        return response.json()["results"]
```

**Note:** Fingerprint must be passed from the orchestrator through to the tool.

### New Tools

#### `list_my_documents`

List user's uploaded documents. Available to all agents.

**Parameters:**
- `fingerprint` (required): User's browser fingerprint

**Returns:** List of uploaded documents with id, filename, page_count, uploaded_at

**Use case:** User asks "What documents have I uploaded?" or agent needs to reference user's personal documents.

#### `delete_my_document`

Delete a user's uploaded document and all its chunks.

**Parameters:**
- `fingerprint` (required): User's browser fingerprint
- `document_id` (required): ID of document to delete

**Returns:** Success/failure status

**Use case:** User asks "Delete my maintenance manual" - agent finds the document and deletes it.

### Tool Registration

All agents (FAA, NRC, DoD) will have:
- Modified `search_indexed_content` (already exists, updated implementation)
- New `list_my_documents` 
- New `delete_my_document`

Document upload is handled via dedicated API endpoint, not as a tool (too large for tool payload).

#### `fetch_personal_document`

Fetch the complete text of an uploaded personal document for grounding.

**Parameters:**
- `document_id` (required): Document ID from `list_my_documents` or search results
- `fingerprint` (required): User's browser fingerprint (injected by orchestrator)

**Behavior:**
- Retrieves all chunks from the index and reassembles full document text
- Caches full text in conversation memory for follow-up searches
- Returns first 50,000 characters (~25 pages)
- If truncated, appends message offering to search remainder

**Returns:** Full document text with title header, or truncated text with search offer

**Use case:** User asks detailed questions about an uploaded document. Agent fetches complete text to ensure accurate, grounded answers.

#### `search_personal_document`

Semantically search within a personal document for specific topics.

**Parameters:**
- `document_id` (required): Document ID
- `query` (required): Topic or question to search for
- `fingerprint` (required): User's browser fingerprint (injected by orchestrator)

**Behavior:**
- Reads full text from conversation memory cache (or fetches if not cached)
- Splits text into paragraphs
- Generates embeddings for query and paragraphs (Cohere embed-v3)
- Returns top matching passages with ±1 paragraph context

**Returns:** Up to 10,000 characters of relevant passages

**Use case:** Document was truncated, user asks about topic not in visible portion. Agent searches full text semantically.

---

## Document Grounding (Anti-Hallucination)

### Problem

When users upload documents and ask questions about them, the agent may:
1. Find partial matches in chunked search results
2. Fill gaps using training data or general knowledge
3. Confuse information from training data with document content
4. Hallucinate details that sound plausible but aren't in the document

For aerospace compliance, this is unacceptable. Every claim must be traceable to a source document.

### Solution: Full Document Fetch + Semantic Search

Instead of relying only on search result snippets, provide tools to retrieve and search the complete document text.

### Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Initial fetch limit | 50,000 chars | ~25 pages, covers most docs fully |
| Full text search limit | 100,000 chars | ~50 pages, handles large reports |
| Search result limit | 10,000 chars | Focused excerpts, not full dump |
| Search method | Semantic (Cohere embed-v3) | Finds related content, not just keywords |
| Context window | ±1 paragraph | Preserves readability around matches |

### Memory Cache

Full document text is cached in conversation memory:

| Aspect | Detail |
|--------|--------|
| Cache key | `personal_doc_{document_id}` |
| Populated by | `fetch_personal_document` |
| Read by | `search_personal_document` |
| Scope | Single conversation |
| Cleared | When conversation ends |

### System Prompt Grounding Rules

Added to all agent system prompts:

```
## Answering Questions About Personal/Uploaded Documents

When search results include personal documents (marked [Personal Document]), use 
`fetch_personal_document` to retrieve the complete text before answering.

**Grounding Rules:**

1. **Document content is authoritative** - What the document says IS what it says. 
   Quote directly when possible.

2. **Connect to regulations, don't invent** - You MAY reference official CFR/AC 
   documents to provide regulatory context (e.g., "This test report addresses 
   §25.1309 requirements"). You MUST NOT add technical claims that aren't in 
   the uploaded document OR official indexed regulations.

3. **Distinguish your sources clearly:**
   - "According to your uploaded document..."
   - "Per 14 CFR §25.1309..."
   - "The document does not address [X]"

4. **If information is missing, say so** - Never fill gaps with general knowledge. 
   State: "This document does not contain information about [topic]. Would you 
   like me to search FAA regulations instead?"

5. **Handle truncated documents:** If fetch_personal_document indicates truncation 
   and the user asks about something not in the visible portion, use 
   `search_personal_document` to find relevant passages in the full text.

6. **No external sources** - Do not cite press reports, Wikipedia, or training 
   data. Only cite: (a) the uploaded document, (b) official regulatory documents 
   from the index/DRS/APS.
```

### Comparison: Personal vs Regulatory Document Handling

| Aspect | Regulatory (CFR/DRS) | Personal Documents |
|--------|---------------------|-------------------|
| Search | `search_indexed_content` (chunks) | `search_indexed_content` (chunks) |
| Full fetch | `fetch_cfr_section`, `fetch_drs_document` | `fetch_personal_document` |
| Truncation | 15K chars (DRS) / unlimited (CFR) | 50K chars initial |
| Fallback search | N/A (re-search index) | `search_personal_document` |
| Size limit | No limit | 100K chars |
| Grounding | Trust indexed content | Strict: only cite document |

### Why This Matters for Aerospace Compliance

1. **Traceability** - Auditors require every compliance claim to trace to a document
2. **No speculation** - A hallucinated requirement could cause safety issues
3. **Explicit gaps** - "Not found" is better than invented information
4. **Regulatory context** - Connecting uploaded docs to CFR sections helps engineers

---

## Search Proxy API

### POST `/search`

Query the index with enforced fingerprint filtering.

**Request:**
```json
{
  "query": "maintenance procedures",
  "index": "faa-index",
  "fingerprint": "abc123...",
  "top": 10
}
```

**Behavior:**
- Automatically adds filter: `(owner_fingerprint eq null or owner_fingerprint eq 'abc123...')`
- Cannot be bypassed - hardcoded in search service

**Response:**
```json
{
  "results": [
    {
      "id": "doc-chunk-1",
      "title": "Company Maintenance Manual",
      "content": "...",
      "source": "personal",
      "citation": "maintenance-manual.pdf p.12",
      "score": 0.95
    }
  ]
}
```

### POST `/index`

Add document chunks to the index.

**Request:**
```json
{
  "index": "faa-index",
  "fingerprint": "abc123...",
  "documents": [
    {
      "id": "abc123-doc1-chunk1",
      "title": "Company Maintenance Manual",
      "content": "Chunk text here...",
      "source": "personal",
      "doc_type": "user_upload",
      "citation": "maintenance-manual.pdf p.1",
      "owner_fingerprint": "abc123...",
      "uploaded_at": "2026-01-27T10:30:00Z",
      "page_count": 45
    }
  ]
}
```

**Validation:**
- `owner_fingerprint` in documents must match request `fingerprint`
- Cannot upload with `owner_fingerprint: null` (regulatory docs protected)

### GET `/documents?fingerprint={fp}&index={index}`

List documents uploaded by a user.

**Response:**
```json
{
  "documents": [
    {
      "id": "abc123-doc1",
      "title": "Company Maintenance Manual",
      "filename": "maintenance-manual.pdf",
      "uploaded_at": "2026-01-27T10:30:00Z",
      "page_count": 45,
      "chunk_count": 12
    }
  ]
}
```

### DELETE `/documents/{id}?fingerprint={fp}&index={index}`

Delete a user's document and all its chunks.

**Validation:**
- Document's `owner_fingerprint` must match request fingerprint
- Returns 403 if attempting to delete someone else's document

---

## Backend API

### POST `/documents`

Upload a PDF document.

**Request:** `multipart/form-data`
- `file`: PDF file (max 20MB)
- `fingerprint`: User's browser fingerprint

**Process:**
1. Validate file (PDF, size limit)
2. Compute file hash (SHA-256) for deduplication
3. Check if user already uploaded document with same hash → reject if duplicate
4. Extract text using PyMuPDF (`fitz`)
5. If text extraction yields little/no content, use PyMuPDF's OCR fallback
6. Chunk text (~1000 tokens per chunk)
7. Generate embeddings for each chunk
8. Forward to search proxy `/index` endpoint (include file_hash)
9. Return upload status

**Deduplication:**
- Compute SHA-256 hash of uploaded file
- Query search proxy for existing documents with same hash and fingerprint
- If found, return 409 Conflict with message "Document already uploaded"
- Hash stored in index for future duplicate checks

**OCR Fallback Logic:**
- If PyMuPDF text extraction yields < 100 characters per page average, assume scanned document
- Use PyMuPDF's built-in OCR capability (`page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)` with OCR fallback)
- Combine extracted text and proceed with chunking

**Response:**
```json
{
  "id": "abc123-doc1",
  "title": "maintenance-manual.pdf",
  "page_count": 45,
  "chunk_count": 12,
  "status": "indexed"
}
```

### GET `/documents?fingerprint={fp}`

List user's documents (proxies to search service).

### DELETE `/documents/{id}?fingerprint={fp}`

Delete a document (proxies to search service).

---

## Frontend UI

### My Documents Panel

Location: Collapsible panel in the sidebar (below conversation history)

**States:**

1. **Empty State**
   - Icon + "No documents uploaded"
   - "Upload PDFs to include your own documents in search results"
   - Upload button

2. **Documents List**
   - List of uploaded documents
   - Each shows: filename, page count, upload date
   - Delete button (with confirmation)
   - Upload button at bottom

3. **Uploading State**
   - Progress indicator
   - Filename being uploaded
   - Cancel button (optional)

4. **Processing State**
   - "Indexing document..."
   - Spinner

5. **Error State**
   - Error message
   - Retry button

### Upload Methods

1. **Drag & Drop**: Drag PDF onto the panel or chat area
2. **Browse**: Click upload button, file picker opens
3. **Paste**: Ctrl+V / Cmd+V when chat is focused (if clipboard contains PDF)

### Limits Display

Show: "3 of 20 documents used" with progress bar

---

## Limits & Constraints

| Constraint | Value | Rationale |
|------------|-------|-----------|
| Max file size | 20 MB | Balance between utility and cost |
| Max documents per user | 20 | Prevent abuse, manageable index size |
| Supported formats | PDF only | Simplicity, most common format |
| Max chunks per document | 100 | ~100k tokens, roughly 400 pages |
| Chunk size | ~1000 tokens | Balance retrieval precision vs context |
| OCR timeout | 60 seconds | Prevent long-running OCR jobs blocking |

---

## Dependencies

### Python Packages
- `PyMuPDF` (fitz) - PDF text extraction with built-in OCR support
- `httpx` - Async HTTP client for search proxy communication

### System Dependencies
- None required - PyMuPDF handles PDF rendering and OCR internally

---

## Security Considerations

### Fingerprint Enforcement
- Search service hardcodes fingerprint filter on every query
- Backend has no Azure AI Search credentials
- Cannot query without fingerprint
- Cannot query other users' documents

### Upload Validation
- Search service validates `owner_fingerprint` in uploaded documents matches request fingerprint
- Cannot upload documents with `null` fingerprint (regulatory protection)

### Deletion Protection
- Can only delete documents where `owner_fingerprint` matches request fingerprint
- Search service enforces this, not backend

---

## Implementation Phases

### Phase 1: Infrastructure (Week 1)

**Resource Group & Monitoring:**
- [ ] Create `e-cfr-rg` resource group
- [ ] Create `e-cfr-log-analytics` Log Analytics Workspace
- [ ] Create `e-cfr-app-insights` Application Insights (linked to Log Analytics)

**Data & Search:**
- [ ] Create `e-cfr-ai-search-service` (Azure AI Search, Basic tier)
- [ ] Create indexes with new schema (owner_fingerprint, uploaded_at, page_count, file_hash)
- [ ] Create `ecfrstorage` storage account with containers (documents, logs, uploads)
- [ ] Create `e-cfr-postgres` PostgreSQL Flexible Server
- [ ] Copy existing blob cache content from old storage account
- [ ] Migrate existing indexed documents (with owner_fingerprint = null)
- [ ] Migrate PostgreSQL data (usage, feedback tables)

**AI Services:**
- [ ] Create `e-cfr-ai-services` (or reuse existing - Cohere embeddings are shared)

**Compute:**
- [ ] Create `e-cfr-app-service-plan` (Linux, B1 or higher)

### Phase 2: Search Proxy (Week 2)
- [ ] Create `e-cfr-search-proxy` App Service
- [ ] Implement POST `/search` with fingerprint enforcement
- [ ] Implement POST `/index` with validation
- [ ] Implement GET `/documents`
- [ ] Implement DELETE `/documents/{id}`
- [ ] Deploy and test

### Phase 3: Backend Migration (Week 3)
- [ ] Remove Azure AI Search credentials from backend config
- [ ] Update search tool to call search service instead
- [ ] Add POST `/documents` endpoint with PDF processing
- [ ] Add GET `/documents` endpoint (proxy)
- [ ] Add DELETE `/documents/{id}` endpoint (proxy)
- [ ] Deploy `e-cfr-agent-backend`

### Phase 4: Frontend (Week 4)
- [ ] Add My Documents panel component
- [ ] Implement upload UI (drag-drop, browse, paste)
- [ ] Implement documents list with delete
- [ ] Add upload progress indicators
- [ ] Handle error states
- [ ] Update deployment

### Phase 5: Cutover (Week 5)
- [ ] DNS cutover from old resources
- [ ] Monitor for issues
- [ ] Decommission old `faa-agent-*` resources

---

## Implementation Details

### Backend Configuration

Add to `backend/app/config.py`:

```python
# Search Proxy
search_proxy_url: str = "http://localhost:8001"  # Default for local dev
```

Environment variable: `SEARCH_PROXY_URL`

### Local Development

Use `scripts/dev_start.sh` to start both services:

```bash
#!/bin/bash
# Start search proxy on port 8001
cd backend/search_proxy && uvicorn main:app --port 8001 &
SEARCH_PROXY_PID=$!

# Start backend on port 8000
cd backend && uvicorn app.main:app --port 8000 &
BACKEND_PID=$!

echo "Search proxy running on http://localhost:8001 (PID: $SEARCH_PROXY_PID)"
echo "Backend running on http://localhost:8000 (PID: $BACKEND_PID)"
echo "Press Ctrl+C to stop both services"

trap "kill $SEARCH_PROXY_PID $BACKEND_PID 2>/dev/null" EXIT
wait
```

### Explicit Index Parameter

All search proxy endpoints require an explicit `index` parameter:

| Endpoint | Index Parameter |
|----------|----------------|
| `POST /search` | `index` in JSON body |
| `POST /index` | `index` in JSON body |
| `GET /documents` | `index` query param |
| `DELETE /documents/{id}` | `index` query param |

Valid index values: `faa-agent`, `nrc-agent`, `dod-agent`

### Index Schema Migration Script

Run `scripts/update_index_schema.py` to add new fields to existing indexes:

```bash
# Preview changes (no modifications)
python scripts/update_index_schema.py --dry-run

# Apply changes to a specific index
python scripts/update_index_schema.py --index faa-agent

# Apply changes to all indexes
python scripts/update_index_schema.py --all
```

---

## Open Questions

1. **Document expiration**: Should personal documents expire after 90 days of inactivity?
2. **Sharing**: Future phase to allow sharing documents with specific users?
3. **Notifications**: Notify user when document finishes indexing (if they navigate away)?

---

## Appendix: Index Schema (Complete)

```json
{
  "name": "faa-index",
  "fields": [
    {"name": "id", "type": "Edm.String", "key": true},
    {"name": "title", "type": "Edm.String", "searchable": true},
    {"name": "content", "type": "Edm.String", "searchable": true},
    {"name": "source", "type": "Edm.String", "filterable": true},
    {"name": "doc_type", "type": "Edm.String", "filterable": true},
    {"name": "citation", "type": "Edm.String"},
    {"name": "owner_fingerprint", "type": "Edm.String", "filterable": true},
    {"name": "uploaded_at", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true},
    {"name": "page_count", "type": "Edm.Int32"},
    {"name": "file_hash", "type": "Edm.String", "filterable": true},
    {"name": "embedding", "type": "Collection(Edm.Single)", "dimensions": 1024, "vectorSearchProfile": "default"}
  ]
}
```
