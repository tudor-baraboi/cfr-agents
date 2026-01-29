"""
Tool registry for Claude.

Tools are defined here and executed by the orchestrator.
Each tool has a definition (JSON schema) and an implementation function.
"""

import logging
from typing import Any

from app.tools.fetch_cfr import fetch_cfr_section, TOOL_DEFINITION as FETCH_CFR_TOOL
from app.tools.search_indexed import search_indexed_content, TOOL_DEFINITION as SEARCH_TOOL
from app.tools.drs import (
    search_drs,
    fetch_drs_document,
    SEARCH_DRS_DEFINITION,
    FETCH_DRS_DOCUMENT_DEFINITION,
)
from app.tools.documents import (
    list_my_documents,
    delete_my_document,
    LIST_MY_DOCUMENTS_DEFINITION,
    DELETE_MY_DOCUMENT_DEFINITION,
)

logger = logging.getLogger(__name__)

# Tool definitions for Claude API
# Format: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    SEARCH_TOOL,  # Search indexed content first
    FETCH_CFR_TOOL,  # Fetch specific CFR sections
    SEARCH_DRS_DEFINITION,  # Search DRS for Advisory Circulars
    FETCH_DRS_DOCUMENT_DEFINITION,  # Fetch specific DRS documents
    LIST_MY_DOCUMENTS_DEFINITION,  # List user's uploaded documents
    DELETE_MY_DOCUMENT_DEFINITION,  # Delete user's uploaded documents
]

# Tool implementations: name -> async function
_TOOL_IMPLEMENTATIONS: dict[str, Any] = {
    "search_indexed_content": search_indexed_content,
    "fetch_cfr_section": fetch_cfr_section,
    "search_drs": search_drs,
    "fetch_drs_document": fetch_drs_document,
    "list_my_documents": list_my_documents,
    "delete_my_document": delete_my_document,
}


async def execute_tool(name: str, input_data: dict[str, Any]) -> str:
    """Execute a tool by name with given input."""
    if name not in _TOOL_IMPLEMENTATIONS:
        logger.warning(f"Unknown tool: {name}")
        return f"Error: Unknown tool '{name}'"
    
    try:
        result = await _TOOL_IMPLEMENTATIONS[name](**input_data)
        return str(result)
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return f"Error executing {name}: {e}"
