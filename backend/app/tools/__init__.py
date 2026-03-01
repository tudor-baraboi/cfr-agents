"""
Tool implementations for Claude agents.

Each module defines tool functions and their JSON schema definitions.
Tools are registered per-agent in app/agents/__init__.py.

Modules:
- fetch_cfr: Fetch CFR sections from eCFR API
- search_indexed: Search Azure AI Search index
- drs: FAA DRS API (Advisory Circulars, etc.)
- aps: NRC ADAMS Public Search API
- documents: Personal document management (BYOD)
"""
