#!/usr/bin/env python3
"""
Create Azure AI Search index with vector search and personal document fields.
"""

import httpx
import json

import os

SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "https://ecfrsearch.search.windows.net")
API_KEY = os.getenv("AZURE_SEARCH_KEY", "")

if not API_KEY:
    print("Error: AZURE_SEARCH_KEY environment variable not set")
    exit(1)

INDEX_SCHEMA = {
    "name": "faa-agent",
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "filterable": True, "searchable": False},
        {"name": "content", "type": "Edm.String", "searchable": True, "retrievable": True},
        {"name": "title", "type": "Edm.String", "searchable": True, "retrievable": True, "filterable": True},
        {"name": "source_type", "type": "Edm.String", "filterable": True, "facetable": True, "retrievable": True},
        {"name": "cfr_title", "type": "Edm.Int32", "filterable": True, "retrievable": True},
        {"name": "cfr_part", "type": "Edm.Int32", "filterable": True, "retrievable": True},
        {"name": "cfr_section", "type": "Edm.String", "filterable": True, "retrievable": True},
        {"name": "document_number", "type": "Edm.String", "filterable": True, "retrievable": True},
        {"name": "document_url", "type": "Edm.String", "retrievable": True},
        {"name": "effective_date", "type": "Edm.DateTimeOffset", "filterable": True, "sortable": True, "retrievable": True},
        {"name": "chunk_index", "type": "Edm.Int32", "filterable": True, "retrievable": True},
        {"name": "total_chunks", "type": "Edm.Int32", "retrievable": True},
        {"name": "parent_id", "type": "Edm.String", "filterable": True, "retrievable": True},
        # Personal document fields
        {"name": "owner_fingerprint", "type": "Edm.String", "filterable": True, "retrievable": True},
        {"name": "uploaded_at", "type": "Edm.DateTimeOffset", "filterable": True, "sortable": True, "retrievable": True},
        {"name": "page_count", "type": "Edm.Int32", "retrievable": True},
        {"name": "file_hash", "type": "Edm.String", "filterable": True, "retrievable": True},
        {"name": "file_name", "type": "Edm.String", "filterable": True, "retrievable": True, "searchable": True},
        # Vector field
        {
            "name": "content_vector",
            "type": "Collection(Edm.Single)",
            "searchable": True,
            "retrievable": False,
            "dimensions": 1024,
            "vectorSearchProfile": "vector-profile"
        }
    ],
    "vectorSearch": {
        "algorithms": [
            {
                "name": "hnsw-algorithm",
                "kind": "hnsw",
                "hnswParameters": {
                    "m": 4,
                    "efConstruction": 400,
                    "efSearch": 500,
                    "metric": "cosine"
                }
            }
        ],
        "profiles": [
            {"name": "vector-profile", "algorithm": "hnsw-algorithm"}
        ]
    },
    "semantic": {
        "configurations": [
            {
                "name": "semantic-config",
                "prioritizedFields": {
                    "prioritizedContentFields": [{"fieldName": "content"}],
                    "prioritizedKeywordsFields": [],
                    "titleField": {"fieldName": "title"}
                }
            }
        ]
    }
}


def create_index(index_name: str):
    """Create the search index."""
    schema = INDEX_SCHEMA.copy()
    schema["name"] = index_name
    
    url = f"{SEARCH_ENDPOINT}/indexes/{index_name}?api-version=2024-07-01"
    
    response = httpx.put(
        url,
        headers={
            "Content-Type": "application/json",
            "api-key": API_KEY,
        },
        json=schema,
        timeout=30.0
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code in (200, 201):
        print(f"✅ Index '{index_name}' created successfully!")
    else:
        print(f"❌ Failed to create index '{index_name}'")
    
    return response.status_code in (200, 201)


if __name__ == "__main__":
    import sys
    
    indexes = ["faa-agent"]
    if len(sys.argv) > 1:
        if sys.argv[1] == "--all":
            indexes = ["faa-agent", "nrc-agent", "dod-agent"]
        else:
            indexes = [sys.argv[1]]
    
    for idx in indexes:
        print(f"\nCreating index: {idx}")
        create_index(idx)
