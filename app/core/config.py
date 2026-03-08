"""
Configuration management using Pydantic Settings.
Loads configuration from environment variables.
"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # AWS Configuration
    aws_region: str = "eu-west-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    # AWS Profile name (e.g., "power-user-access") - takes priority over access keys
    aws_profile: Optional[str] = None
    # Inference Profile ARN (REQUIRED)
    # Get this from AWS Bedrock Console -> Inference Profiles
    # Example: "arn:aws:bedrock:eu-west-1:442080794900:inference-profile/eu.meta.llama3-2-3b-instruct-v1:0"
    bedrock_inference_profile_arn: Optional[str] = None

    # Qdrant Configuration
    qdrant_url: str = "https://api.qdrant.io"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_name: str = "_knowledge_base"

    # Embedding Model Configuration
    embedding_provider: str = "bedrock"  # Options: 'bedrock', 'local', 'openai'
    # Bedrock model or local model name
    embedding_model: str = "amazon.titan-embed-text-v2:0"
    # Embedding dimension (for Titan V2: 1024, 512, or 256. Default: 1024)
    embedding_dimension: int = 1024
    openai_api_key: Optional[str] = None  # Only needed if provider is 'openai'

    # API Security
    api_key: str = ""
    api_key_header: str = "X-API-Key"

    # Application Configuration
    log_level: str = "INFO"
    cache_ttl_seconds: int = 3600
    rate_limit_per_minute: int = 60
    max_question_length: int = 2000
    max_retrieval_chunks: int = 5
    # Score threshold for vector similarity search (lower = more results, higher = more precise)
    # Recommended: 0.5-0.6 for better recall, 0.7+ for high precision
    score_threshold: float = 0.5
    # Adjacent chunk retrieval: retrieve surrounding chunks for better context
    include_adjacent_chunks: bool = True
    # Number of chunks before/after to retrieve (default: 1 = ±1 chunk)
    adjacent_chunks_window: int = 1

    # Conversation Memory Configuration
    # Enable conversation history/memory (requires Redis)
    enable_conversation_memory: bool = True
    # Maximum conversation history messages to include in prompt (default: 10)
    max_conversation_history: int = 10
    # Conversation TTL in hours (default: 24 hours)
    conversation_ttl_hours: int = 24

    # Query Rewriting Configuration
    # Enable query rewriting to fix typos and improve search results
    enable_query_rewriting: bool = True
    # Use LLM for advanced query rewriting (slower but better, requires Bedrock)
    enable_llm_query_rewriting: bool = False

    # Redis Configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0

    # Stash/Bitbucket Configuration
    stash_enabled: bool = False
    stash_base_url: str = "https://stash.example.com"
    stash_username: Optional[str] = None
    stash_password: Optional[str] = None
    # Bearer token (alternative to username/password)
    stash_token: Optional[str] = None
    # True for Bitbucket Cloud, False for Bitbucket Server/Stash
    stash_is_bitbucket_cloud: bool = False
    stash_workspace: Optional[str] = None  # Required for Bitbucket Cloud
    stash_max_results: int = 10
    stash_timeout: int = 10

    # Confluence Configuration
    confluence_enabled: bool = False
    confluence_base_url: str = "https://confluence.example.com"
    confluence_username: Optional[str] = None
    confluence_password: Optional[str] = None
    # Bearer token (alternative to username/password)
    confluence_token: Optional[str] = None
    # Use /wiki/rest/api/search endpoint (CQL search) instead of /rest/api/content/search
    confluence_use_wiki_search: bool = False
    # Comma-separated list of space keys to search
    confluence_space_keys: Optional[str] = None
    confluence_max_results: int = 10
    confluence_timeout: int = 10

    # MongoDB Configuration (for product_scraper_api)
    mongodb_enabled: bool = False
    mongodb_uri: Optional[str] = None
    mongodb_database_name: str = "ProductReview"
    mongodb_products_collection: str = "products"
    mongodb_reviews_collection: str = "marketplace_reviews"
    mongodb_max_results: int = 10
    mongodb_timeout: int = 10

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        # Ignore extra fields in .env file (like old bedrock_api_key, bedrock_bearer_token)
        extra="ignore"
    )


# Global settings instance
settings = Settings()
