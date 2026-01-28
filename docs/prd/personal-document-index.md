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
4. Extract text using pypdf
5. If text extraction yields little/no content, run OCR using pdf2image + pytesseract
6. Chunk text (~1000 tokens per chunk)
7. Generate embeddings for each chunk
8. Forward to search service `/index` endpoint (include file_hash)
9. Return upload status

**Deduplication:**
- Compute SHA-256 hash of uploaded file
- Query search proxy for existing documents with same hash and fingerprint
- If found, return 409 Conflict with message "Document already uploaded"
- Hash stored in index for future duplicate checks

**OCR Fallback Logic:**
- If pypdf extracts < 100 characters per page average, assume scanned document
- Convert PDF pages to images using pdf2image (poppler)
- Run pytesseract OCR on each page image
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
- `pypdf` - Text extraction from native PDFs
- `pdf2image` - Convert PDF pages to images for OCR
- `pytesseract` - Python wrapper for Tesseract OCR
- `Pillow` - Image processing

### System Dependencies (App Service)
- `poppler-utils` - Required by pdf2image for PDF rendering
- `tesseract-ocr` - OCR engine (install via apt on Linux App Service)

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
