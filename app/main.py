"""
Main FastAPI application initialization.
"""
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.api.routes import router, init_services, init_limiter
from app.services.vector_db import VectorDBService
from app.services.bedrock_service import BedrockService
from app.services.cache_service import CacheService
from app.services.conversation_service import ConversationService
from app.services.query_rewriter import QueryRewriter
from app.services.stash_service import StashService
from app.services.confluence_service import ConfluenceService
from app.services.mongodb_service import MongoDBService

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Sparky AI Assistant API",
    description="Backend service for Microsoft Teams AI assistant",
    version="1.0.0"
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Initialize rate limiter in routes
init_limiter(limiter)

# Add validation error handler for better debugging
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors for debugging."""
    body = await request.body()
    logger.error(f"Validation error on {request.url.path}")
    logger.error(f"Validation errors: {exc.errors()}")
    logger.error(f"Request body: {body.decode('utf-8', errors='ignore')}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "body": body.decode('utf-8', errors='ignore')
        }
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
logger.info("=" * 60)
logger.info("Initializing Sparky AI Assistant Services")
logger.info("=" * 60)
logger.info(f"Embedding Provider: {settings.embedding_provider}")
logger.info(f"Embedding Model: {settings.embedding_model}")
logger.info(f"Embedding Dimension: {settings.embedding_dimension}")
logger.info(f"Qdrant URL: {settings.qdrant_url}")
logger.info(f"Qdrant Collection: {settings.qdrant_collection_name}")
logger.info(f"Stash Enabled: {settings.stash_enabled}")
logger.info(f"Confluence Enabled: {settings.confluence_enabled}")
logger.info(f"Confluence Wiki Search: {settings.confluence_use_wiki_search}")
logger.info(f"MongoDB Enabled: {settings.mongodb_enabled}")
logger.info("=" * 60)

logger.info("Initializing VectorDBService...")
vector_db_service = VectorDBService()
logger.info("✓ VectorDBService initialized")

logger.info("Initializing BedrockService...")
bedrock_service = BedrockService()
logger.info("✓ BedrockService initialized")

logger.info("Initializing CacheService...")
cache_service = CacheService()
logger.info(f"✓ CacheService initialized (enabled: {cache_service.enabled})")

logger.info("Initializing ConversationService...")
conversation_service = ConversationService()
logger.info(
    f"✓ ConversationService initialized (enabled: {conversation_service.enabled})")

logger.info("Initializing QueryRewriter...")
query_rewriter = QueryRewriter()
logger.info(f"✓ QueryRewriter initialized")
logger.info(f"  Query rewriting enabled: {settings.enable_query_rewriting}")
logger.info(f"  LLM rewriting enabled: {settings.enable_llm_query_rewriting}")

logger.info("Initializing StashService...")
stash_service = StashService()
logger.info(f"✓ StashService initialized (enabled: {stash_service.enabled})")

logger.info("Initializing ConfluenceService...")
confluence_service = ConfluenceService()
logger.info(
    f"✓ ConfluenceService initialized (enabled: {confluence_service.enabled})")

logger.info("Initializing MongoDBService...")
mongodb_service = MongoDBService()
logger.info(
    f"✓ MongoDBService initialized (enabled: {mongodb_service.enabled})")

logger.info("=" * 60)
logger.info("All services initialized successfully")
logger.info("=" * 60)

# Initialize services in routes
init_services(
    vector_db_service,
    bedrock_service,
    cache_service,
    conversation_service,
    query_rewriter,
    stash_service,
    confluence_service,
    mongodb_service
)

# Include router
app.include_router(router)
