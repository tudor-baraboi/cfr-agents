from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    
    # Azure AI Services (for embeddings - Cohere)
    azure_ai_services_endpoint: str = ""
    azure_ai_services_key: str = ""
    azure_ai_services_embedding_deployment: str = "cohere-embed"
    
    # Azure AI Search
    azure_search_endpoint: str = ""
    azure_search_key: str = ""
    azure_search_index: str = "faa-agent"
    azure_search_index_nrc: str = "nrc-agent"
    azure_search_index_dod: str = "dod-agent"
    
    # Search Proxy (for personal document isolation)
    search_proxy_url: str = "http://localhost:8001"  # Default for local dev
    
    # External APIs - FAA
    ecfr_api_base_url: str = "https://www.ecfr.gov/api/versioner/v1"
    drs_api_base_url: str = "https://drs.faa.gov/api/drs"
    drs_api_key: str = ""
    
    # External APIs - NRC (ADAMS Public Search)
    aps_api_key: str = ""  # Get from https://adams-api-developer.nrc.gov/
    
    # Azure Blob Storage (document cache)
    azure_blob_connection_string: str = ""
    azure_blob_container_name: str = "documents"
    
    # Authentication
    admin_codes: str = ""  # Comma-separated list of admin codes (unlimited access)
    jwt_secret: str = ""   # Secret for signing JWT tokens (required for auth)
    daily_request_limit: int = 15  # Number of requests per fingerprint per day
    
    # Feature flags
    cache_enabled: bool = True
    auto_index_on_cache_hit: bool = True
    
    # App Settings
    debug: bool = False
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars (e.g., old trial_codes)
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
