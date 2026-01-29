"""
Search Proxy Configuration.

This service has the ONLY access to Azure AI Search credentials.
It enforces fingerprint-based filtering on all search requests.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Search proxy settings loaded from environment variables."""

    # Azure AI Search (THIS is the only place these credentials exist)
    azure_search_endpoint: str = ""
    azure_search_key: str = ""

    # Azure AI Services (for embeddings - Cohere)
    azure_ai_services_endpoint: str = ""
    azure_ai_services_key: str = ""
    azure_ai_services_embedding_deployment: str = "cohere-embed"

    # Valid index names
    valid_indexes: list[str] = ["faa-agent", "nrc-agent", "dod-agent"]

    # App Settings
    debug: bool = False
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",  # Read from current working directory (backend/)
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
