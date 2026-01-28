"""
Seed the Azure AI Search index with CFR sections.

Usage:
    python -m scripts.seed_index

Fetches key CFR sections from eCFR and indexes them.
"""

import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path

import httpx

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.tools.fetch_cfr import fetch_cfr_section

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Key CFR sections to index (Title 14 - Aeronautics)
SECTIONS_TO_INDEX = [
    # Part 25 - Transport Category Airplanes (most important)
    (25, "1301"),  # Function and installation
    (25, "1309"),  # Equipment, systems, and installations (CRITICAL)
    (25, "1316"),  # Electrical and electronic system lightning protection
    (25, "1317"),  # HIRF protection
    (25, "581"),   # Fatigue evaluation
    (25, "571"),   # Damage tolerance
    (25, "613"),   # Material strength properties
    (25, "629"),   # Aeroelastic stability
    (25, "631"),   # Bird strike damage
    (25, "671"),   # Control systems - general
    (25, "1355"),  # Distribution system
    (25, "1357"),  # Circuit protective devices
    
    # Part 21 - Certification Procedures
    (21, "15"),    # Application for type certificate
    (21, "17"),    # Designation of applicable regulations
    (21, "20"),    # Compliance with applicable requirements
    (21, "21"),    # Issue of type certificate
    (21, "31"),    # Type design
    (21, "33"),    # Inspection and tests
    
    # Part 23 - Normal Category Airplanes
    (23, "2500"),  # Airplane level systems requirements
    (23, "2505"),  # Function and installation
    (23, "2510"),  # Equipment, systems, and installations
]


# Cohere embed-v3-english produces 1024-dimensional vectors
EMBEDDING_DIMENSIONS = 1024


async def generate_embedding(text: str, settings, input_type: str = "document") -> list[float] | None:
    """
    Generate embedding using Azure AI Services Cohere model.
    
    Args:
        text: Text to embed
        settings: App settings with Azure credentials
        input_type: 'document' for indexing, 'query' for search queries
    """
    if not settings.azure_ai_services_endpoint or not settings.azure_ai_services_key:
        logger.warning("Azure AI Services not configured, skipping embeddings")
        return None
    
    # Azure AI Model Inference API format for Cohere
    url = f"{settings.azure_ai_services_endpoint}/models/embeddings?api-version=2024-05-01-preview"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.azure_ai_services_key}",
                    "Content-Type": "application/json",
                    "extra-parameters": "pass-through",
                },
                json={
                    "input": [text[:8000]],  # Truncate to fit model limit
                    "model": settings.azure_ai_services_embedding_deployment,
                    "input_type": input_type,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return None


async def index_document(doc: dict, settings) -> bool:
    """Upload a document to Azure AI Search."""
    endpoint = settings.azure_search_endpoint
    index = settings.azure_search_index
    api_key = settings.azure_search_key
    
    url = f"{endpoint}/indexes/{index}/docs/index?api-version=2024-07-01"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": api_key,
                },
                json={
                    "value": [
                        {
                            "@search.action": "upload",
                            **doc,
                        }
                    ]
                },
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Index error for {doc.get('id')}: {e}")
            return False


async def seed_index():
    """Fetch CFR sections and index them."""
    settings = get_settings()
    
    if not settings.azure_search_endpoint:
        logger.error("Azure Search not configured")
        return
    
    logger.info(f"Seeding index with {len(SECTIONS_TO_INDEX)} CFR sections...")
    
    success_count = 0
    
    for part, section in SECTIONS_TO_INDEX:
        logger.info(f"Fetching 14 CFR {part}.{section}...")
        
        # Fetch CFR content
        content = await fetch_cfr_section(title=14, part=part, section=section)
        
        if content.startswith("Error") or content.startswith("Section not found"):
            logger.warning(f"Skipping {part}.{section}: {content[:50]}")
            continue
        
        # Generate document ID
        doc_id = hashlib.md5(f"14-cfr-{part}-{section}".encode()).hexdigest()
        
        # Create document
        doc = {
            "id": doc_id,
            "title": f"14 CFR §{part}.{section}",
            "content": content,
            "source": f"14 CFR Part {part}",
            "doc_type": "cfr",
            "citation": f"14 CFR §{part}.{section}",
        }
        
        # Generate embedding if OpenAI is configured
        embedding = await generate_embedding(content, settings)
        if embedding:
            doc["embedding"] = embedding
        
        # Index document
        if await index_document(doc, settings):
            success_count += 1
            logger.info(f"✓ Indexed {part}.{section}")
        else:
            logger.error(f"✗ Failed to index {part}.{section}")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)
    
    logger.info(f"\nDone! Indexed {success_count}/{len(SECTIONS_TO_INDEX)} documents.")


if __name__ == "__main__":
    asyncio.run(seed_index())
