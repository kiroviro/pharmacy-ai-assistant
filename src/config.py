"""
Centralized configuration for ViaPharma chatbot.

Uses pydantic-settings for type-safe configuration with environment variable support.
All hardcoded values should be moved here.
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field


# Check if pydantic-settings is available, fallback to dataclass if not
try:
    from pydantic_settings import BaseSettings
    PYDANTIC_SETTINGS_AVAILABLE = True
except ImportError:
    from pydantic import BaseModel as BaseSettings
    PYDANTIC_SETTINGS_AVAILABLE = False


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Environment variables are prefixed with VIAPHARMA_ (e.g., VIAPHARMA_API_PORT=8080)
    """

    # ==========================================================================
    # API Server
    # ==========================================================================
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    debug: bool = Field(default=False, description="Enable debug mode")

    # ==========================================================================
    # Models
    # ==========================================================================
    medgemma_model_path: str = Field(
        default="./models/medgemma-4b-it-bf16",
        description="Path to MedGemma model"
    )
    medgemma_max_tokens: int = Field(default=200, description="Max tokens for MedGemma")
    medgemma_temperature: float = Field(default=0.3, description="Temperature for MedGemma")

    # Translation models (Helsinki-NLP)
    translation_model_bg_en: str = Field(
        default="Helsinki-NLP/opus-mt-bg-en",
        description="Bulgarian to English translation model"
    )
    translation_model_en_bg: str = Field(
        default="Helsinki-NLP/opus-mt-en-bg",
        description="English to Bulgarian translation model"
    )

    # Embedding model for product search
    embedding_model: str = Field(
        default="paraphrase-multilingual-MiniLM-L12-v2",
        description="Sentence transformer model for embeddings"
    )

    # ==========================================================================
    # Database
    # ==========================================================================
    chromadb_path: str = Field(default="data/chromadb", description="ChromaDB storage path")
    chromadb_collection: str = Field(default="viapharma_products", description="ChromaDB collection name")

    # ==========================================================================
    # Product Settings
    # ==========================================================================
    product_base_url: str = Field(
        default="https://viapharma.us/products",
        description="Base URL for product links"
    )
    product_data_dir: str = Field(default="output", description="Directory with product CSV files")

    # ==========================================================================
    # Pipeline Settings
    # ==========================================================================
    vector_search_top_k: int = Field(default=10, description="Number of candidates from vector search")
    llm_refine_top_k: int = Field(default=3, description="Number of products after LLM refinement")
    translation_cache_size: int = Field(default=1000, description="Max entries in translation cache")

    # ==========================================================================
    # Security & Limits
    # ==========================================================================
    max_message_length: int = Field(default=2000, description="Maximum user message length")
    min_message_length: int = Field(default=2, description="Minimum user message length")
    rate_limit_per_minute: int = Field(default=30, description="Max requests per minute per IP")
    request_timeout_seconds: int = Field(default=60, description="Request timeout in seconds")
    cors_origins: str = Field(
        default="https://viapharma.us,http://localhost:3000,http://localhost:8080",
        description="Comma-separated list of allowed CORS origins"
    )

    # ==========================================================================
    # Logging
    # ==========================================================================
    log_level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    log_json: bool = Field(default=False, description="Use JSON format for logs")
    log_file: Optional[str] = Field(default=None, description="Optional log file path")

    # ==========================================================================
    # Feature Flags
    # ==========================================================================
    enable_rate_limiting: bool = Field(default=True, description="Enable rate limiting")
    enable_request_logging: bool = Field(default=True, description="Log all requests")
    prewarm_models: bool = Field(default=True, description="Pre-load models on startup")

    if PYDANTIC_SETTINGS_AVAILABLE:
        model_config = {
            "env_prefix": "VIAPHARMA_",
            "env_file": ".env",
            "env_file_encoding": "utf-8",
            "extra": "ignore",
        }


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Settings are loaded once and cached for the lifetime of the application.
    To reload settings, call get_settings.cache_clear() first.
    """
    return Settings()


# Convenience function for accessing settings
def settings() -> Settings:
    """Shorthand for get_settings()."""
    return get_settings()


# ==========================================================================
# Environment-specific presets
# ==========================================================================

def get_development_settings() -> Settings:
    """Get settings optimized for development."""
    return Settings(
        debug=True,
        log_level="DEBUG",
        log_json=False,
        enable_rate_limiting=False,
        prewarm_models=False,  # Faster startup for development
    )


def get_production_settings() -> Settings:
    """Get settings optimized for production."""
    return Settings(
        debug=False,
        log_level="INFO",
        log_json=True,
        enable_rate_limiting=True,
        prewarm_models=True,
    )
