# 003: DoD Contract Agent Extension Plan

**Status:** Planning  
**Date:** 2026-01-21  
**Context:** Extend the multi-agent backend to support DoD (Department of Defense) procurement and security compliance queries for Title 32 CFR (National Defense) and Title 48 CFR (FAR/DFARS).

---

## Overview

Add DoD Contract Agent alongside the existing FAA and NRC agents, reusing the existing CFR fetch infrastructure with a self-evolving search index. No new external APIs or tools required.

## Architecture Decision

**Approach:** Minimal extension - reuse existing tools with new agent configuration

The DoD agent reuses the same `fetch_cfr_section` tool (which already supports any CFR title) and `search_indexed_content`. Claude determines the correct title parameter (32 or 48) from context.

---

## Component Analysis

### Shared Components (No Changes Needed)

| Component | File | Reason |
|-----------|------|--------|
| CFR fetch tool | `tools/fetch_cfr.py` | Already supports any CFR title via `title` parameter |
| Search tool | `tools/search_indexed.py` | Already supports index override via `index_name` parameter |
| Cache infrastructure | `services/cache.py` | Same blob storage, same `cfr_key()` method |
| Indexer | `services/indexer.py` | Same embedding model and indexing logic |
| Conversation history | `services/conversation.py` | Same PostgreSQL schema |
| Auth | `routers/auth.py` | Same authentication |
| Orchestrator loop | `services/orchestrator.py` | Same Claude streaming logic |
| WebSocket infrastructure | `main.py` | Same streaming protocol |

### Agent-Specific Components

| Component | FAA Agent | NRC Agent | DoD Agent |
|-----------|-----------|-----------|-----------|
| Search index | `faa-agent` | `nrc-agent` | `dod-agent` |
| System prompt | FAA regulations focus | NRC documents focus | FAR/DFARS/Title 32 focus |
| Tools | `fetch_cfr`, `search_drs` | `search_aps`, `fetch_aps` | `fetch_cfr`, `search_indexed` |
| CFR Titles | 14 (Aeronautics) | 10 (Energy) | 32 (National Defense), 48 (FAR/DFARS) |
| External APIs | eCFR, DRS | eCFR, APS | eCFR only |

---

## Storage Architecture: Cache vs Index

### Blob Cache (Shared Across All Agents)

The document cache is **source-based**, not agent-based. All agents share the same blob container:

```
{container_name}/
├── cfr/                         # All CFR documents (any title)
│   ├── 14-25-1309.json          # FAA: Title 14 Part 25
│   ├── 10-50-55a.json           # NRC: Title 10 Part 50
│   ├── 32-117-15.json           # DoD: Title 32 (Defense)
│   └── 48-252-204-7012.json     # DoD: Title 48 (DFARS)
├── drs/                         # FAA DRS documents
│   └── AC-25.1309-1A.json
└── aps/                         # NRC ADAMS documents
    └── ML13095A205.json
```

**Cache key patterns:**
- CFR: `cfr/{title}-{part}-{section}.json` 
- DRS: `drs/{doc_type}-{doc_number}.json`
- APS: `aps/{accession_number}.json`

This is **correct behavior** - a CFR section is the same document regardless of which agent fetches it. The cache prevents duplicate API calls.

### Search Index (Agent-Specific)

The **index** is what's agent-specific. Each agent has its own Azure AI Search index:

| Agent | Index Name | Contents |
|-------|------------|----------|
| FAA | `faa-agent` | Title 14 CFR + FAA ACs, Orders |
| NRC | `nrc-agent` | Title 10 CFR + NUREGs, RGs |
| DoD | `dod-agent` | Title 32 + Title 48 CFR |

When a document is fetched:
1. **Cache:** Stored by source (e.g., `cfr/48-252-204-7012.json`)
2. **Index:** Routed to calling agent's index (e.g., `dod-agent`)

This separation allows:
- Cache reuse if multiple agents need the same CFR section
- Agent-specific search results (FAA users don't see DFARS)

---

## Key Insight: Existing Tools Are Sufficient

The `fetch_cfr_section` tool accepts a `title` parameter and works with any CFR title:

```python
# FAA question → Claude calls:
fetch_cfr_section(title=14, part=25, section="1309")

# DoD DFARS question → Claude calls:
fetch_cfr_section(title=48, part=252, section="204-7012")

# DoD security question → Claude calls:
fetch_cfr_section(title=32, part=117, section="15")
```

Claude's training includes knowledge that:
- FAR = Title 48 CFR Parts 1-53
- DFARS = Title 48 CFR Parts 201-253
- DoD security regulations = Title 32 CFR

The system prompt provides additional domain context.

---

## Implementation Steps

### Step 0: Refactor - Context Injection for Index Routing

**Problem:** Currently, NRC uses wrapper functions (`search_indexed_content_nrc`) to route to the correct index. This pattern doesn't scale - each new agent requires new wrapper functions.

**Solution:** Have the orchestrator automatically inject the agent's `search_index` into tools that support it.

#### 0a. Modify ALL Tools to Accept `index_name` Parameter

All tools that read from or write to the index need `index_name`:

| Tool | File | Operation | Needs `index_name` |
|------|------|-----------|-------------------|
| `search_indexed_content` | `search_indexed.py` | Read | ✅ Already has it |
| `fetch_cfr_section` | `fetch_cfr.py` | Write (indexes fetched CFR) | ✅ Add it |
| `fetch_drs_document` | `drs.py` | Write (indexes fetched DRS docs) | ✅ Add it |
| `fetch_aps_document` | `aps.py` | Write (indexes fetched APS docs) | ✅ Add it |

**File:** `backend/app/tools/fetch_cfr.py`

```python
async def fetch_cfr_section(
    part: int,
    section: str,
    title: int = 14,
    date: str | None = None,
    index_name: str | None = None,  # NEW: injected by orchestrator
) -> str:
    # ... existing code ...
    
    schedule_indexing(
        ...,
        index_name=index_name,  # NEW: route to correct index
    )
```

**File:** `backend/app/tools/drs.py`

```python
async def fetch_drs_document(
    document_guid: str,
    doc_type: str,
    index_name: str | None = None,  # NEW: injected by orchestrator
) -> str:
    # ... existing code ...
    
    schedule_indexing(
        ...,
        index_name=index_name,  # NEW: route to correct index
    )
```

**File:** `backend/app/tools/aps.py`

```python
async def fetch_aps_document(
    accession_number: str,
    index_name: str | None = None,  # NEW: injected by orchestrator
) -> str:
    # ... existing code ...
    
    schedule_indexing(
        ...,
        index_name=index_name,  # NEW: route to correct index
    )
```

**File:** `backend/app/services/indexer.py`

Ensure `schedule_indexing` and `index_document` accept and use `index_name`:

```python
def schedule_indexing(..., index_name: str | None = None):
    # Pass index_name to background task

async def index_document(..., index_name: str | None = None):
    # Use index_name when calling upload_to_index
    await upload_to_index(doc, index_name=index_name)
```

#### 0b. Modify Orchestrator to Auto-Inject Index

**File:** `backend/app/services/orchestrator.py`

```python
import inspect

async def execute_tool_with_config(
    name: str,
    input_data: dict[str, Any],
    agent_config: AgentConfig,
) -> str:
    if name not in agent_config.tool_implementations:
        return f"Error: Unknown tool '{name}'"
    
    tool_func = agent_config.tool_implementations[name]
    
    # Auto-inject agent's search index if tool accepts it
    sig = inspect.signature(tool_func)
    if "index_name" in sig.parameters and "index_name" not in input_data:
        input_data["index_name"] = agent_config.search_index
    
    return await tool_func(**input_data)
```

#### 0c. Remove Wrapper Functions

**File:** `backend/app/agents/__init__.py`

Delete `search_indexed_content_nrc` wrapper. Update NRC config to use base function:

```python
# BEFORE (wrapper pattern)
NRC_AGENT_CONFIG = AgentConfig(
    tool_implementations={
        "search_indexed_content": search_indexed_content_nrc,  # Wrapper
    },
)

# AFTER (context injection)
NRC_AGENT_CONFIG = AgentConfig(
    search_index="nrc-agent",  # Single source of truth
    tool_implementations={
        "search_indexed_content": search_indexed_content,  # Base function
    },
)
```

#### Benefits of This Refactor

| Aspect | Before (Wrappers) | After (Context Injection) |
|--------|-------------------|---------------------------|
| Add new agent | Create N wrappers | Just set `search_index` |
| Code duplication | High | None |
| Index routing | Manual per wrapper | Automatic |
| Maintenance | Update each wrapper | Update once |

---

### Step 1: Add DoD Configuration

**File:** `backend/app/config.py`

Add environment variable:
```python
# DoD Agent
azure_search_index_dod: str = "dod-agent"
```

### Step 2: Register DoD Agent

**File:** `backend/app/agents/__init__.py`

Add DoD system prompt and agent configuration:

```python
DOD_SYSTEM_PROMPT = """You are a DoD Contract Agent - an expert assistant for Department of Defense 
acquisition and contract compliance.

You help contracting officers, program managers, and contractors navigate:
- Federal Acquisition Regulation (FAR) - Title 48 CFR Parts 1-53
- Defense Federal Acquisition Regulation Supplement (DFARS) - Title 48 CFR Parts 201-253
- DoD security regulations - Title 32 CFR (National Defense)
- NIST 800-171 and CMMC cybersecurity requirements
- Small business contracting requirements
- Cost accounting standards

When fetching CFR sections:
- Use title=48 for FAR and DFARS clauses
- Use title=32 for defense security regulations

Always cite the specific CFR section, FAR clause, or DFARS clause number in your responses.
"""

DOD_AGENT_CONFIG = AgentConfig(
    name="dod",
    search_index="dod-agent",
    system_prompt=DOD_SYSTEM_PROMPT,
    tool_definitions=[
        SEARCH_INDEXED_TOOL,  # Reuse
        FETCH_CFR_TOOL,       # Reuse
    ],
    tool_implementations={
        "search_indexed_content": search_indexed_content_dod,
        "fetch_cfr_section": fetch_cfr_section,
    },
)

# Add to registry
AGENT_CONFIGS["dod"] = DOD_AGENT_CONFIG
```

Also update `get_agent_config()` to handle `"dod"` agent type.

### Step 3: Add DoD Frontend Configuration

**File:** `frontend/src/config.ts`

Add DoD to the agent type and configuration:

```typescript
export type AgentType = 'faa' | 'nrc' | 'dod';

const DOD_CONFIG: AgentConfig = {
  branding: {
    name: 'DoD Contract Agent',
    shortName: 'DoD Agent',
    title: 'DoD Contract Agent',
    subtitle: 'Defense acquisition & compliance assistance',
    placeholder: 'Ask about FAR, DFARS, or contract requirements...',
    welcomeTitle: 'How can I help you today?',
    welcomeText: 'I can help you navigate FAR clauses, DFARS requirements, and DoD contract compliance.',
    primaryColor: '#FFD700',  // Gold
    logoText: 'DoD',
    sessionStoragePrefix: 'dod',
  },
  exampleQueries: [
    "What are the DFARS 252.204-7012 cybersecurity requirements?",
    "Explain the Buy American Act requirements in FAR 52.225",
    "What clauses apply to cost-reimbursement contracts?",
    "How do I comply with small business subcontracting plans?",
    "What is required for CUI handling under NIST 800-171?",
  ],
};

// Add to AGENT_CONFIGS
export const AGENT_CONFIGS: Record<AgentType, AgentConfig> = {
  faa: FAA_CONFIG,
  nrc: NRC_CONFIG,
  dod: DOD_CONFIG,
};
```

### Step 4: Add DoD Citation Extraction (Frontend)

The frontend extracts citations from message content and displays them in a "References" section. Each agent has its own extraction patterns.

**File:** `frontend/src/store.ts`

Add `extractDodCitations()` function:

```typescript
/**
 * Extracts DoD citations from message content (e.g., FAR 52.219, DFARS 252.204-7012)
 */
function extractDodCitations(content: string): string[] {
  const citations = new Set<string>();
  let match;
  
  // FAR references: FAR XX.XXX or FAR Part XX
  const farRegex = /FAR\s+(?:Part\s+)?(\d+(?:\.\d+)?(?:-\d+)?)/gi;
  while ((match = farRegex.exec(content)) !== null) {
    citations.add(`FAR ${match[1]}`);
  }
  
  // DFARS references: DFARS 2XX.XXX-XXXX
  const dfarsRegex = /DFARS\s+(\d+\.\d+-?\d*)/gi;
  while ((match = dfarsRegex.exec(content)) !== null) {
    citations.add(`DFARS ${match[1]}`);
  }
  
  // Title 48 CFR: 48 CFR XX.XXX
  const cfr48Regex = /48\s*CFR\s*§?\s*(\d+\.\d+(?:-\d+)?)/gi;
  while ((match = cfr48Regex.exec(content)) !== null) {
    citations.add(`48 CFR ${match[1]}`);
  }
  
  // Title 32 CFR: 32 CFR XX.XXX
  const cfr32Regex = /32\s*CFR\s*§?\s*(\d+\.\d+)/gi;
  while ((match = cfr32Regex.exec(content)) !== null) {
    citations.add(`32 CFR ${match[1]}`);
  }
  
  // NIST SP 800-XXX references
  const nistRegex = /NIST\s+(?:SP\s+)?800-(\d+)/gi;
  while ((match = nistRegex.exec(content)) !== null) {
    citations.add(`NIST SP 800-${match[1]}`);
  }
  
  // CMMC references
  const cmmcRegex = /CMMC\s+(?:Level\s+)?(\d+(?:\.\d+)?)/gi;
  while ((match = cmmcRegex.exec(content)) !== null) {
    citations.add(`CMMC ${match[1]}`);
  }
  
  return Array.from(citations);
}

// Update extractCitations() to handle 'dod' agent
function extractCitations(content: string): string[] {
  switch (AGENT) {
    case 'nrc': return extractNrcCitations(content);
    case 'dod': return extractDodCitations(content);
    default: return extractFaaCitations(content);
  }
}
```

**Citation patterns for DoD:**

| Pattern | Example | Extracted As |
|---------|---------|--------------|
| FAR clause | "FAR 52.219-8" | `FAR 52.219-8` |
| DFARS clause | "DFARS 252.204-7012" | `DFARS 252.204-7012` |
| Title 48 CFR | "48 CFR 52.212" | `48 CFR 52.212` |
| Title 32 CFR | "32 CFR 117.15" | `32 CFR 117.15` |
| NIST standards | "NIST SP 800-171" | `NIST SP 800-171` |
| CMMC level | "CMMC Level 2" | `CMMC 2` |

### Step 5: Create Empty Search Index

Run Azure CLI to create the `dod-agent` index with the same schema as existing indexes:

```bash
# Using existing index schema
az search index create \
  --service-name faa-ai-search \
  --resource-group faa-agent \
  --name dod-agent \
  --fields @index-schema.json
```

Or use the existing seed script pattern to create an empty index.

### Step 6: Deploy DoD Frontend

Create a new Azure Static Web App for the DoD frontend:

```bash
# Build with DoD agent configuration
VITE_AGENT=dod npm run build

# Deploy to new SWA instance
swa deploy ./dist --env production
```

---

## Self-Evolving Index Behavior

The DoD agent starts with an **empty search index**. As users ask questions:

1. User asks: "What does DFARS 252.204-7012 require?"
2. Agent calls `fetch_cfr_section(title=48, part=252, section="204-7012")`
3. eCFR API returns the full clause text
4. Document is cached to blob storage
5. Background task promotes document to `dod-agent` search index
6. Future queries find it via semantic search

No manual seeding required - the index learns from usage patterns.

---

## Relevant CFR Titles for DoD

| Title | Coverage | Common Use Cases |
|-------|----------|------------------|
| Title 48 Parts 1-53 | Federal Acquisition Regulation (FAR) | General procurement rules, standard clauses |
| Title 48 Parts 201-253 | DFARS | Defense-specific requirements, cybersecurity |
| Title 32 | National Defense | Security clearances, CUI, NIST 800-171 references |

---

## Files Changed Summary

| File | Change |
|------|--------|
| `backend/app/services/orchestrator.py` | Add context injection for `index_name` |
| `backend/app/tools/fetch_cfr.py` | Add `index_name` parameter |
| `backend/app/tools/drs.py` | Add `index_name` parameter |
| `backend/app/tools/aps.py` | Add `index_name` parameter |
| `backend/app/agents/__init__.py` | Remove wrappers, add `DOD_SYSTEM_PROMPT` and `DOD_AGENT_CONFIG` |
| `backend/app/config.py` | Add `azure_search_index_dod` setting |
| `frontend/src/config.ts` | Add `dod` to `AgentType` and `DOD_CONFIG` |
| `frontend/src/store.ts` | Add `extractDodCitations()` function |

**No new tools needed** - existing `fetch_cfr_section` and `search_indexed_content` are reused.

---

## Example Queries

| Query | Expected Tool Calls |
|-------|---------------------|
| "What are the DFARS cybersecurity requirements?" | `search_indexed_content` → `fetch_cfr_section(title=48, part=252, section="204-7012")` |
| "Explain FAR 52.219 small business clauses" | `fetch_cfr_section(title=48, part=52, section="219")` |
| "What is CUI and how do I protect it?" | `search_indexed_content` → `fetch_cfr_section(title=32, part=2002, ...)` |
| "Buy American Act requirements" | `search_indexed_content` → `fetch_cfr_section(title=48, part=25, ...)` |
