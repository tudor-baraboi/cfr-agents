# FAA Certification Agent - Project Instructions

## Trial Token Usage

When the user asks about trial token usage, remaining requests, or token statistics, run this script:

```bash
python scripts/check_trial_usage.py
```

This will query the Azure backend and display current usage for all trial codes.

## Overview
This project is an FAA (Federal Aviation Administration) agent application.

The goal is to build a multi-turn conversational AI agent that helps aviation professionals navigate FAA regulations and guidance documents. The system provides authoritative, traceable answers to certification questions by intelligently searching indexed content, fetching complete regulatory documents, and walking document reference chains across multiple conversation turns. The agent uses Claude API for orchestration, Azure AI Search for fast semantic retrieval, and external APIs (eCFR and DRS) for comprehensive regulatory access. A key innovation is automatic indexing of fetched documents, making the system self-improving as it learns from usage patterns.

## System Components

**Frontend: SolidJS chat interface (Azure Static Web Apps)**
- WebSocket for real-time streaming responses
- Shows citations, tool usage, and document references

**Backend: FastAPI application (Azure App Service)**
- WebSocket handler for conversations
- Executes tools and manages state
- Auto-indexes documents fetched from CFR and DRS

**Orchestrator: Claude API (Anthropic)**
- Decides which tools to call
- Walks document graph when references are needed
- Synthesizes answers with citations

**How Multi-Turn Context Works:**
Claude is stateless - it only knows what you send in each request. For multi-turn conversations:
1. Backend loads conversation history from PostgreSQL
2. Builds message array with previous user/assistant messages
3. Sends complete history + tool definitions to Claude API
4. Claude sees full context and responds appropriately
5. New turn saved back to PostgreSQL for next request

Example: User asks "What about test procedures?" - Claude receives the entire previous conversation about HIRF requirements, understands the context, and searches for HIRF-specific test guidance.

**Data Layer:**
- Azure AI Search: Vector index (core CFR + core ACs + auto-indexed CFR/DRS docs)
- PostgreSQL: Conversation history and state
- Blob Storage: Cached documents (both CFR and DRS)

## Available Tools

**Search Tools:**
- `search_indexed_content()` - Semantic search on vector index
- `search_drs()` - Keyword search across all DRS documents

**Fetch Tools:**
- `fetch_cfr_section()` - Get complete CFR section text
- `fetch_drs_document()` - Get specific DRS document
- `get_cfr_references()` - Extract document relationships

**Index Management:**
- `index_document()` - Add document to vector index
- Auto-indexing: Any CFR or DRS document fetched gets indexed automatically

## Typical Query Flow

**Simple question:**
1. Search vector index → find answer → respond

**Complex question (document graph):**
1. Search index → find CFR §25.1317
2. Fetch complete section → see reference to §25.1309
3. Fetch §25.1309 → synthesize complete answer

**Obscure topic:**
1. Search index → no results
2. Search DRS API → find relevant AC
3. Fetch DRS document → answer question
4. **Auto-index document for next time**

**Explicit section request:**
1. User: "Show me §25.1309(b)"
2. Fetch CFR directly → respond

## Self-Improving Behavior

- System learns from usage patterns
- Frequently-accessed DRS documents migrate into index
- Index grows smarter over time
- Reduces API calls and improves response speed

## Tool Configuration

Tools defined in each Claude API call with:
- Name and description (helps Claude choose correctly)
- Input schema (parameters and types)
- System prompt guides Claude to follow references and index important documents

## Tech Stack
- **Backend:** Python with FastAPI
- **Frontend:** TypeScript with SolidJS
- **AI Orchestration:** Claude API (Anthropic)
- **Search:** Azure AI Search (vector index)
- **Database:** PostgreSQL (conversation state)
- **Storage:** Azure Blob Storage (document cache)
- **Hosting:** Azure App Service (backend), Azure Static Web Apps (frontend)

## Project Structure
```
/backend        - FastAPI application
/frontend       - SolidJS chat interface
/tools          - Tool implementations for Claude
/infra          - Azure infrastructure (Bicep/Terraform)
```

## Coding Guidelines

**AI-First Principles:** This codebase is designed to be written and maintained by LLMs. Optimize for model reasoning, regeneration, and debugging — not human aesthetics.

### Structure
- Use a consistent, predictable project layout
- Group code by feature/screen; keep shared utilities minimal
- Create simple, obvious entry points
- Identify shared structure before scaffolding multiple files; use framework-native composition patterns (layouts, base templates, providers, shared components)
- Duplication requiring the same fix in multiple places is a code smell

### Architecture
- Prefer flat, explicit code over abstractions or deep hierarchies
- Avoid clever patterns, metaprogramming, and unnecessary indirection
- Minimize coupling so files can be safely regenerated

### Functions and Modules
- Keep control flow linear and simple
- Use small-to-medium functions; avoid deeply nested logic
- Pass state explicitly; avoid globals

### Naming and Comments
- Use descriptive-but-simple names
- Comment only to note invariants, assumptions, or external requirements

### Logging and Errors
- Emit detailed, structured logs at key boundaries
- Make errors explicit and informative
- Log tool calls and responses for debugging

### Regenerability
- Write code so any file/module can be rewritten from scratch without breaking the system
- Prefer clear, declarative configuration (JSON/YAML/etc.)

### Platform Use
- Use platform conventions directly and simply without over-abstracting
- Follow FastAPI patterns for backend, SolidJS patterns for frontend

### Modifications
- When extending/refactoring, follow existing patterns
- Prefer full-file rewrites over micro-edits unless told otherwise

### Quality
- Favor deterministic, testable behavior
- Keep tests simple and focused on verifying observable behavior

### Domain-Specific
- Always include citations when referencing FAA documents
- Include error handling for all external API calls (eCFR, DRS)


## Key Concepts
- **CFR** - Code of Federal Regulations (e.g., 14 CFR Part 25 for transport aircraft)
- **AC** - Advisory Circular (FAA guidance documents)
- **DRS** - Document Retrieval System (FAA document API)
- **eCFR** - Electronic Code of Federal Regulations API
- **HIRF** - High-Intensity Radiated Fields (common certification topic)
- **Document Graph** - Network of cross-references between FAA documents

## DRS API Reference

**IMPORTANT:** Before working with the DRS API (implementing features, debugging issues, or modifying DRS-related code), always consult these documentation files:

1. **[docs/drs-api-documentation.md](../docs/drs-api-documentation.md)** - Complete DRS API technical documentation including:
   - All API endpoints (data-pull, download, filtered)
   - Request/response formats
   - Authentication (x-api-key header)
   - Pagination (750 docs per request, offset parameter)
   - Filter validation rules
   - Error handling

2. **[docs/drs-metadata-mapping.md](../docs/drs-metadata-mapping.md)** - Document types and metadata mapping including:
   - All 97 document types with API names (e.g., `AC`, `ADFRAWD`, `ORDERS`, `TSO`)
   - Metadata field names for filtering and parsing responses
   - Data types (TEXT, DATE, ARRAY)
   - Default sort fields per document type

**Key DRS API details:**
- Base URL: `https://drs.faa.gov/api/drs`
- Returns max 750 documents per request (use `offset` for pagination)
- Supports keyword search via `documentFilters.Keyword` in filtered endpoint
- Date filters require exactly 2 values: `["start", "end"]` in `YYYY-MM-DD` format
- Max 5 filters, max 10 values per filter

## NRC ADAMS Public Search (APS) API Reference

**IMPORTANT:** Before working with the NRC ADAMS APS API (implementing features, debugging issues, or modifying APS-related code), always consult this documentation file:

**[docs/aps-api-documentation.md](../docs/aps-api-documentation.md)** - Complete ADAMS Public Search API technical documentation including:
- Get Document and Search Document Library endpoints
- JSON request/response formats
- Authentication (Ocp-Apim-Subscription-Key header)
- Filter objects for text and date properties
- Document properties available for search
- Query examples for Part 21, Inspection Reports, and more

**Key APS API details:**
- Base URL: `https://adams-api.nrc.gov/aps/api/search`
- Requires subscription key from https://adams-api-developer.nrc.gov/
- Uses JSON POST body for search queries (not URL parameters)
- Supports `filters` (AND) and `anyFilters` (OR) arrays
- Text filter operators: `equals`, `notequals`, `contains`, `notcontains`, `starts`, `notstarts`
- Date filter operators: `ge` (on or after), `le` (on or before), `eq` (equals)
- Date format: `YYYY-MM-DD`
- Supports Main Library (since Nov 1999) and Legacy Library (pre-Nov 1999)

**Note:** This API replaced the deprecated Web-Based ADAMS (WBA) API in February 2026.

## DoD Clause Logic Service (CLS) API Reference

**IMPORTANT:** Before working with the CLS API (implementing features, debugging issues, or modifying CLS-related code), always consult this documentation file:

**[docs/cls-api-documentation.md](../docs/cls-api-documentation.md)** - Complete CLS Web Services API technical documentation including:
- All API endpoints (reserve, register, status, retrieve)
- Request/response formats
- Authentication (basic auth → JWT exchange)
- Document ID (PIID) format validation rules
- Payload validation (required, optional, conditional elements)
- Error codes and responses

**Key CLS API details:**
- Test URL: `https://cls-test.fedmall.mil/clsws`
- Production URL: `https://cls.fedmall.mil/clsws`
- Uses query parameters for user_id, system_id, document_id
- Register endpoint requires Auto Answer JSON payload in request body
- Status endpoint returns 200/204 to indicate document readiness
- Retrieve endpoint returns XML clause document (CLS Response schema)
- Document IDs follow PIID format (13 chars for base, +hyphen+suffix for mods/amendments)

## Development Notes
- Claude is stateless; backend manages conversation history
- Auto-indexing improves search over time
- Always follow document references to provide complete answers
- Use semantic search first, fall back to DRS API for obscure topics
