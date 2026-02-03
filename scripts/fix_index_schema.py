#!/usr/bin/env python3
"""Fix Azure AI Search index schema by adding missing fields."""
import json
import subprocess
import sys

import os

SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "https://ecfrsearch.search.windows.net")
API_KEY = os.getenv("AZURE_SEARCH_KEY", "")
API_VERSION = "2024-07-01"

if not API_KEY:
    print("Error: AZURE_SEARCH_KEY environment variable not set")
    exit(1)

def get_index(index_name):
    """Fetch current index schema."""
    result = subprocess.run([
        "curl", "-s",
        f"{SEARCH_ENDPOINT}/indexes/{index_name}?api-version={API_VERSION}",
        "-H", f"api-key: {API_KEY}"
    ], capture_output=True, text=True)
    return json.loads(result.stdout)

def update_index(index_name, schema):
    """Update index schema."""
    result = subprocess.run([
        "curl", "-s", "-X", "PUT",
        f"{SEARCH_ENDPOINT}/indexes/{index_name}?api-version={API_VERSION}",
        "-H", "Content-Type: application/json",
        "-H", f"api-key: {API_KEY}",
        "-d", json.dumps(schema)
    ], capture_output=True, text=True)
    return result.stdout

def main():
    index_name = sys.argv[1] if len(sys.argv) > 1 else "faa-agent"
    print(f"Updating index: {index_name}")
    
    # Get current schema
    index = get_index(index_name)
    existing = [f["name"] for f in index["fields"]]
    print(f"Existing fields ({len(existing)}): {existing}")
    
    # New fields to add
    new_fields = []
    if "source" not in existing:
        new_fields.append({
            "name": "source",
            "type": "Edm.String",
            "searchable": False,
            "filterable": True,
            "retrievable": True,
            "stored": True,
            "sortable": False,
            "facetable": False,
            "key": False,
            "synonymMaps": []
        })
    if "doc_type" not in existing:
        new_fields.append({
            "name": "doc_type",
            "type": "Edm.String",
            "searchable": False,
            "filterable": True,
            "retrievable": True,
            "stored": True,
            "sortable": False,
            "facetable": False,
            "key": False,
            "synonymMaps": []
        })
    if "citation" not in existing:
        new_fields.append({
            "name": "citation",
            "type": "Edm.String",
            "searchable": False,
            "filterable": False,
            "retrievable": True,
            "stored": True,
            "sortable": False,
            "facetable": False,
            "key": False,
            "synonymMaps": []
        })
    
    if not new_fields:
        print("No fields need to be added!")
        return
    
    print(f"Adding fields: {[f['name'] for f in new_fields]}")
    
    # Insert new fields before content_vector (last field)
    index["fields"] = index["fields"][:-1] + new_fields + [index["fields"][-1]]
    
    # Remove @odata fields
    for key in list(index.keys()):
        if key.startswith("@odata"):
            del index[key]
    
    # Update the index
    result = update_index(index_name, index)
    print(f"Result: {result}")
    
    # Verify
    updated = get_index(index_name)
    new_existing = [f["name"] for f in updated["fields"]]
    print(f"Updated fields ({len(new_existing)}): {new_existing}")

if __name__ == "__main__":
    main()
