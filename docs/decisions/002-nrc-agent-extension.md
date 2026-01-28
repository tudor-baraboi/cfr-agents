# 002: NRC Agent Extension Plan

**Status:** Planning  
**Date:** 2026-01-17  
**Context:** Extend the FAA certification agent backend to support NRC (Nuclear Regulatory Commission) document queries using the ADAMS WBA API.

---

## Overview

Add NRC agent functionality alongside the existing FAA agent, reusing shared infrastructure while maintaining separate search indexes, tools, and prompts.

## Architecture Decision

**Approach:** Multi-agent configuration with shared core infrastructure

The same backend serves both FAA and NRC agents, with agent-specific configuration (prompts, tools, search index) passed through the orchestration layer.

---

## Component Analysis

### Shared Components (No Changes Needed)

| Component | File | Reason |
|-----------|------|--------|
| Cache infrastructure | `services/cache.py` | Same blob storage, just add `wba_key()` method |
| Indexer | `services/indexer.py` | Same embedding model and indexing logic |
| Conversation history | `services/conversation.py` | Same PostgreSQL schema |
| Auth | `routers/auth.py` | Same authentication |
| Database | `database.py` | Same connection pool |
| Orchestrator loop | `services/orchestrator.py` | Same Claude streaming logic (parameterized) |
| Embeddings | Cohere embed-v3-english | Same model, same dimensions |
| WebSocket infrastructure | `main.py` | Same streaming protocol |

### Agent-Specific Components

| Component | FAA Agent | NRC Agent |
|-----------|-----------|-----------|
| Search index | `faa-agent` | `nrc-agent` |
| System prompt | FAA regulations focus | NRC documents focus |
| Tools | `drs.py`, `fetch_cfr.py` | `wba.py` |
| Cache folder | `cfr/`, `drs/` | `wba/` |
| External APIs | eCFR, DRS | WBA (ADAMS) |

---

## Implementation Steps

### Step 1: Add NRC Configuration

**File:** `backend/app/config.py`

Add environment variables:
```python
# NRC Agent
AZURE_SEARCH_INDEX_NRC: str = "nrc-agent"
WBA_API_BASE_URL: str = "http://adams.nrc.gov/wba/services/search/advanced/nrc"
```

### Step 2: Create WBA Tools

**File:** `backend/app/tools/wba.py` (new)

Following `drs.py` pattern, implement:
- `search_wba(query, document_type, docket_number, date_range)` — Content and advanced search
- `fetch_wba_document(accession_number)` — Retrieve specific document by accession number

Key differences from DRS:
- No API key required
- Returns XML (need to parse)
- Max 1,000 results per query
- Different query format (pseudo-JSON in URL)

Reference: [docs/wba-api-documentation.md](../wba-api-documentation.md)

### Step 3: Create Agent Registry

**File:** `backend/app/agents/__init__.py` (new)

```python
from dataclasses import dataclass
from typing import List, Dict, Any, Callable

@dataclass
class AgentConfig:
    name: str
    system_prompt: str
    tool_definitions: List[Dict[str, Any]]
    tool_handlers: Dict[str, Callable]
    search_index: str

FAA_AGENT_CONFIG = AgentConfig(
    name="faa",
    system_prompt=FAA_SYSTEM_PROMPT,
    tool_definitions=FAA_TOOL_DEFINITIONS,
    tool_handlers={"search_indexed_content": ..., "fetch_cfr_section": ..., "search_drs": ...},
    search_index="faa-agent",
)

NRC_AGENT_CONFIG = AgentConfig(
    name="nrc",
    system_prompt=NRC_SYSTEM_PROMPT,
    tool_definitions=NRC_TOOL_DEFINITIONS,
    tool_handlers={"search_indexed_content": ..., "search_wba": ..., "fetch_wba_document": ...},
    search_index="nrc-agent",
)

AGENTS = {"faa": FAA_AGENT_CONFIG, "nrc": NRC_AGENT_CONFIG}
```

### Step 4: Refactor Orchestrator

**File:** `backend/app/services/orchestrator.py`

Current state: Hardcoded `SYSTEM_PROMPT` and `TOOL_DEFINITIONS`

Change to accept `AgentConfig` as parameter:
```python
async def run_orchestration(
    conversation_id: str,
    user_message: str,
    agent_config: AgentConfig,  # NEW
) -> AsyncGenerator[StreamEvent, None]:
    # Use agent_config.system_prompt
    # Use agent_config.tool_definitions
    # Use agent_config.tool_handlers
    # Use agent_config.search_index
```

### Step 5: Update WebSocket Endpoint

**File:** `backend/app/main.py`

Add `agent` query parameter:
```python
@app.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: str,
    agent: str = "faa",  # NEW: "faa" or "nrc"
):
    agent_config = AGENTS.get(agent, FAA_AGENT_CONFIG)
    # Pass agent_config to orchestrator
```

Frontend connects with: `ws://host/ws/chat/{id}?agent=nrc`

### Step 6: Extend Cache

**File:** `backend/app/services/cache.py`

Add method:
```python
def wba_key(self, accession_number: str) -> str:
    """Generate blob key for WBA document."""
    return f"wba/{accession_number}.json"
```

Blob structure becomes:
```
documents/
├── cfr/          # FAA CFR sections
├── drs/          # FAA DRS documents
└── wba/          # NRC ADAMS documents
```

---

## Azure Resources Needed

### New Search Index

Create `nrc-agent` index with same schema as `faa-agent`:
- Same Cohere embed-v3-english embeddings (1024 dimensions)
- Same fields: id, content, title, doc_type, source_url, metadata

### Blob Storage

No new containers needed—reuse existing `documents` container with `wba/` prefix.

---

## Frontend Deployment Strategy

**Approach:** Same codebase, two Azure Static Web App deployments with build-time configuration.

### Deployment URLs

| Agent | SWA | URL |
|-------|-----|-----|
| FAA | kind-sky (existing) | `kind-sky.azurestaticapps.net` |
| NRC | (new SWA) | `<nrc-swa>.azurestaticapps.net` |

### Build-time Environment Variables

| Variable | FAA SWA | NRC SWA |
|----------|---------|--------|
| `VITE_AGENT` | `faa` | `nrc` |
| `VITE_APP_TITLE` | FAA Certification Agent | NRC Document Agent |
| Theme color | (current) | (different accent) |

### Frontend Code Changes

**New file:** `frontend/src/config.ts`
```typescript
export const AGENT = import.meta.env.VITE_AGENT || 'faa';
export const APP_TITLE = import.meta.env.VITE_APP_TITLE || 'FAA Agent';
```

**Update:** `frontend/src/websocket.ts`
```typescript
import { AGENT } from './config';
const wsUrl = `${WS_BASE}/ws/chat/${conversationId}?agent=${AGENT}`;
```

**Update:** `frontend/src/App.tsx`
```typescript
import { APP_TITLE } from './config';
// Use APP_TITLE in header/title
```

### Deployment Commands

```bash
# FAA (existing SWA)
VITE_AGENT=faa VITE_APP_TITLE="FAA Certification Agent" npm run build
swa deploy --env production

# NRC (new SWA - create first via Azure Portal or CLI)
VITE_AGENT=nrc VITE_APP_TITLE="NRC Document Agent" npm run build
swa deploy --app-name <nrc-swa-name> --env production
```

### Why Two SWAs?

- ✅ Complete isolation between agents
- ✅ Independent deployments and release cycles
- ✅ Can add custom domains later (faa.example.com, nrc.example.com)
- ✅ Agent-specific branding via environment variables
- ✅ Same source code, no duplication

---

## NRC System Prompt (Draft)

```
You are an expert assistant for nuclear regulatory compliance. You help nuclear 
industry professionals navigate NRC regulations, guidance documents, and 
inspection reports using the ADAMS document system.

Available tools:
- search_indexed_content: Search the NRC document index for relevant content
- search_wba: Search the NRC's ADAMS Public Library for documents
- fetch_wba_document: Retrieve a specific document by accession number

When answering questions:
1. Search the index first for quick answers
2. Use WBA search for broader or recent documents
3. Fetch specific documents when users reference accession numbers
4. Always cite document accession numbers (e.g., ML13095A205)
5. Follow reference chains in documents to provide complete answers
```

---

## Testing Plan

1. **Unit tests:** WBA API parsing, cache key generation
2. **Integration tests:** WBA search returns valid results, document fetch works
3. **E2E tests:** WebSocket with `agent=nrc` routes correctly

---

## Migration Notes

- No breaking changes to existing FAA agent
- Frontend needs update to pass `agent` parameter
- New index `nrc-agent` must be created before NRC agent works

---

## Progress Tracker

- [ ] Step 1: Add NRC configuration to config.py
- [ ] Step 2: Create tools/wba.py
- [ ] Step 3: Create agents/__init__.py registry
- [ ] Step 4: Refactor orchestrator to accept AgentConfig
- [ ] Step 5: Update main.py WebSocket endpoint
- [ ] Step 6: Add wba_key() to cache.py
- [ ] Create nrc-agent search index in Azure
- [ ] Write NRC system prompt
- [ ] Add WBA document type constants
- [ ] Frontend: Create src/config.ts with AGENT and APP_TITLE
- [ ] Frontend: Update websocket.ts to use AGENT param
- [ ] Frontend: Update App.tsx to use APP_TITLE
- [ ] Create new Azure SWA for NRC agent
