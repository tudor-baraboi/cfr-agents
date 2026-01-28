#!/usr/bin/env python3
import os
"""Create the nrc-agent search index in Azure AI Search."""

import urllib.request
import json

SEARCH_ENDPOINT = "https://faa-ai-search.search.windows.net"
API_KEY = os.environ.get("AZURE_SEARCH_KEY", "")
INDEX_NAME = "nrc-agent"

index_schema = {
    "name": INDEX_NAME,
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
        {"name": "title", "type": "Edm.String", "searchable": True},
        {"name": "content", "type": "Edm.String", "searchable": True},
        {"name": "source", "type": "Edm.String", "filterable": True, "facetable": True},
        {"name": "doc_type", "type": "Edm.String", "filterable": True, "facetable": True},
        {"name": "citation", "type": "Edm.String", "searchable": True},
        {
            "name": "embedding",
            "type": "Collection(Edm.Single)",
            "searchable": True,
            "dimensions": 1024,
            "vectorSearchProfile": "default-profile",
        },
    ],
    "vectorSearch": {
        "algorithms": [
            {
                "name": "default-algorithm",
                "kind": "hnsw",
                "hnswParameters": {"metric": "cosine"},
            }
        ],
        "profiles": [{"name": "default-profile", "algorithm": "default-algorithm"}],
    },
}


def create_index():
    url = f"{SEARCH_ENDPOINT}/indexes/{INDEX_NAME}?api-version=2024-07-01"
    data = json.dumps(index_schema).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", "application/json")
    req.add_header("api-key", API_KEY)

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"SUCCESS: Created index '{result.get('name')}'")
            print(f"Fields: {len(result.get('fields', []))}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"ERROR {e.code}: {error_body}")
        return False


def list_indexes():
    url = f"{SEARCH_ENDPOINT}/indexes?api-version=2024-07-01"
    req = urllib.request.Request(url)
    req.add_header("api-key", API_KEY)

    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        indexes = [i["name"] for i in result.get("value", [])]
        print(f"Current indexes: {indexes}")
        return indexes


if __name__ == "__main__":
    print("Listing current indexes...")
    indexes = list_indexes()

    if INDEX_NAME in indexes:
        print(f"Index '{INDEX_NAME}' already exists!")
    else:
        print(f"\nCreating index '{INDEX_NAME}'...")
        create_index()

    print("\nFinal index list:")
    list_indexes()
