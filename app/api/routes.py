"""
API routes for the FastAPI application.
"""
import logging
import time
import json
import hashlib
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Header, Request, Body, Query
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.core.config import settings
from app.core.security import sanitize_input, validate_question, extract_sources_from_chunks
from app.models.schemas import (
    AskRequest, AskResponse, AddEmbeddingRequest, AddEmbeddingResponse
)
from app.services.vector_db import VectorDBService
from app.services.bedrock_service import BedrockService
from app.services.cache_service import CacheService
from app.services.conversation_service import ConversationService
from app.services.query_rewriter import QueryRewriter
from app.services.stash_service import StashService
from app.services.confluence_service import ConfluenceService
from app.services.mongodb_service import MongoDBService

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Rate limiting (will be initialized in main.py)
limiter = None


def init_limiter(limiter_instance):
    """Initialize rate limiter."""
    global limiter
    limiter = limiter_instance


# API Key authentication dependency
async def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Verify API key from request header.

    Args:
        request: FastAPI Request object
        x_api_key: API key from X-API-Key header

    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not settings.api_key:
        # If no API key configured, skip authentication
        logger.warning("API key authentication disabled (no API_KEY set)")
        return

    if not x_api_key or x_api_key != settings.api_key:
        remote_address = get_remote_address(request)
        logger.warning(
            f"Invalid API key attempt from {remote_address}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )


# Initialize services (will be set by main.py)
vector_db_service: Optional[VectorDBService] = None
bedrock_service: Optional[BedrockService] = None
cache_service: Optional[CacheService] = None
conversation_service: Optional[ConversationService] = None
query_rewriter: Optional[QueryRewriter] = None
stash_service: Optional[StashService] = None
confluence_service: Optional[ConfluenceService] = None
mongodb_service: Optional[MongoDBService] = None


def init_services(
    vdb: VectorDBService,
    bedrock: BedrockService,
    cache: CacheService,
    conv: ConversationService,
    qr: QueryRewriter,
    stash: StashService,
    confluence: ConfluenceService,
    mongodb: MongoDBService
):
    """Initialize service instances."""
    global vector_db_service, bedrock_service, cache_service
    global conversation_service, query_rewriter, stash_service, confluence_service, mongodb_service
    vector_db_service = vdb
    bedrock_service = bedrock
    cache_service = cache
    conversation_service = conv
    query_rewriter = qr
    stash_service = stash
    confluence_service = confluence
    mongodb_service = mongodb


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Health status of all services
    """
    logger.info("Health check requested")

    health_status = {
        "vector_db": vector_db_service.health_check() if vector_db_service else False,
        "bedrock": bedrock_service.health_check() if bedrock_service else False,
        "cache": cache_service.health_check() if cache_service else False,
        "conversation_memory": conversation_service.health_check() if conversation_service and settings.enable_conversation_memory else False,
        "stash": stash_service.health_check() if stash_service else False,
        "confluence": confluence_service.health_check() if confluence_service else False,
        "mongodb": mongodb_service.health_check() if mongodb_service else False
    }

    # Log health status
    logger.info("Service Health Status:")
    logger.info(
        f"  VectorDB (Qdrant): {'✓ Healthy' if health_status['vector_db'] else '✗ Unhealthy'}")
    logger.info(
        f"  Bedrock: {'✓ Healthy' if health_status['bedrock'] else '✗ Unhealthy'}")
    logger.info(
        f"  Cache (Redis): {'✓ Healthy' if health_status['cache'] else '✗ Unhealthy'}")
    logger.info(
        f"  Conversation Memory: {'✓ Healthy' if health_status['conversation_memory'] else '✗ Unhealthy'}")
    logger.info(
        f"  Stash: {'✓ Healthy' if health_status['stash'] else '✗ Unhealthy'}")
    logger.info(
        f"  Confluence: {'✓ Healthy' if health_status['confluence'] else '✗ Unhealthy'}")
    logger.info(
        f"  MongoDB: {'✓ Healthy' if health_status['mongodb'] else '✗ Unhealthy'}")

    all_healthy = all([
        health_status['vector_db'],
        health_status['bedrock'],
        health_status['cache']
    ])

    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": health_status
    }


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: Request,
    ask_request: AskRequest,
    _: None = Depends(verify_api_key)
):
    """
    Main endpoint for answering questions.

    Flow:
    1. Validate and sanitize input
    2. Check cache for existing answer
    3. Generate embedding for question
    4. Search vector database for relevant chunks
    5. Build prompt with chunks
    6. Call AWS Bedrock LLM
    7. Return answer with sources

    Args:
        request: FastAPI request object (for rate limiting)
        ask_request: Request containing user and question

    Returns:
        AskResponse with answer and sources

    Raises:
        HTTPException: For validation errors or service failures
    """
    start_time = time.time()

    try:
        # Log request (sanitized)
        logger.info(f"Question received from user: {ask_request.user[:20]}...")

        # Validate question
        is_valid, error_msg = validate_question(ask_request.question)
        if not is_valid:
            logger.warning(f"Invalid question: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        # Sanitize input
        sanitized_question = sanitize_input(ask_request.question)
        if not sanitized_question:
            raise HTTPException(
                status_code=400,
                detail="Question was filtered out by security checks"
            )

        # Rewrite query to improve search results (fix typos, expand terms)
        search_query = sanitized_question
        logger.info(
            f"Query rewriting status: enabled={settings.enable_query_rewriting}")
        if settings.enable_query_rewriting and query_rewriter:
            logger.info(f"Attempting to rewrite query: '{sanitized_question}'")
            search_query = query_rewriter.rewrite_query(
                sanitized_question,
                use_llm=settings.enable_llm_query_rewriting
            )
            if search_query != sanitized_question:
                logger.info(
                    f"✓ Query rewritten: '{sanitized_question}' -> '{search_query}'")
            else:
                logger.info(
                    f"No changes needed for query: '{sanitized_question}'")
        else:
            logger.warning(
                f"Query rewriting is DISABLED - add ENABLE_QUERY_REWRITING=true to .env")

        # Check cache (use original sanitized question for cache key)
        if cache_service:
            cached_result = cache_service.get(sanitized_question)
            if cached_result:
                logger.info("Returning cached answer")
                return AskResponse(
                    answer=cached_result["answer"],
                    sources=cached_result["sources"]
                )

        # Search all enabled sources
        logger.info("Searching all enabled knowledge sources")
        all_chunks = []

        # 1. Search Qdrant vector database
        if vector_db_service:
            try:
                logger.info(
                    f"Searching Qdrant vector database for: '{search_query[:100]}...'")
                query_embedding = vector_db_service.generate_embedding(
                    search_query)
                vector_chunks = vector_db_service.search_similar_chunks(
                    query_embedding=query_embedding,
                    limit=settings.max_retrieval_chunks,
                    score_threshold=settings.score_threshold,
                    include_adjacent=settings.include_adjacent_chunks,
                    adjacent_window=settings.adjacent_chunks_window
                )
                all_chunks.extend(vector_chunks)
                if vector_chunks:
                    # Log top chunk scores for debugging
                    top_scores = [chunk.get("score", 0)
                                  for chunk in vector_chunks[:3]]
                    logger.info(
                        f"✓ Found {len(vector_chunks)} chunks from Qdrant (top scores: {[f'{s:.3f}' for s in top_scores]})")
                else:
                    logger.warning(
                        f"✗ No chunks found from Qdrant (threshold: {settings.score_threshold})")
            except Exception as e:
                logger.warning(f"Qdrant search failed: {str(e)}")
                # Continue with other sources even if Qdrant fails

        # 2. Search Stash/Bitbucket code repositories
        if settings.stash_enabled and stash_service:
            try:
                logger.info("Searching Stash code repositories")
                stash_code_results = stash_service.search_code(
                    sanitized_question)
                all_chunks.extend(stash_code_results)
                logger.info(
                    f"✓ Found {len(stash_code_results)} results from Stash")
            except Exception as e:
                logger.warning(f"✗ Stash search failed: {str(e)}")

        # 3. Search Confluence documentation
        if settings.confluence_enabled and confluence_service:
            try:
                search_type = "wiki search" if settings.confluence_use_wiki_search else "content search"
                logger.info(
                    f"Searching Confluence documentation ({search_type})")
                confluence_results = confluence_service.search_content(
                    sanitized_question)
                all_chunks.extend(confluence_results)
                logger.info(
                    f"✓ Found {len(confluence_results)} results from Confluence")
            except Exception as e:
                logger.warning(f"✗ Confluence search failed: {str(e)}")

        # 4. Search MongoDB for product data and reviews
        if settings.mongodb_enabled and mongodb_service:
            try:
                logger.info("Searching MongoDB product database")

                # Use LLM to extract intent and product keywords
                mongodb_intent = None
                product_keywords = sanitized_question

                if query_rewriter and settings.enable_llm_query_rewriting:
                    try:
                        mongodb_intent = query_rewriter.extract_mongodb_intent(
                            sanitized_question)
                        if mongodb_intent:
                            product_keywords = mongodb_intent.get(
                                "product_keywords", sanitized_question)
                            intent = mongodb_intent.get("intent", "general")
                            logger.info(
                                f"LLM extracted intent: '{intent}', product_keywords: '{product_keywords}'")
                        else:
                            logger.warning(
                                "LLM intent extraction returned None, using fallback")
                    except Exception as e:
                        logger.warning(
                            f"LLM intent extraction failed: {e}, using fallback detection")

                # Route to appropriate MongoDB method based on intent
                mongodb_results = []

                if mongodb_intent:
                    intent = mongodb_intent.get("intent", "general")

                    if intent == "find_most_liked":
                        logger.info(
                            f"Routing to find_most_liked_product with keywords: '{product_keywords}'")
                        mongodb_results = mongodb_service.find_most_liked_product(
                            product_keywords)
                        if not mongodb_results:
                            # Fallback to review analysis
                            logger.info(
                                "No results from find_most_liked, trying analyze_product_reviews")
                            mongodb_results = mongodb_service.analyze_product_reviews(
                                product_keywords)

                    elif intent == "analyze_reviews":
                        logger.info(
                            f"Routing to analyze_product_reviews with keywords: '{product_keywords}'")
                        mongodb_results = mongodb_service.analyze_product_reviews(
                            product_keywords)

                    elif intent == "search_products":
                        logger.info(
                            f"Routing to search_products with keywords: '{product_keywords}'")
                        mongodb_results = mongodb_service.search_products(
                            product_keywords)
                        # Also try review analysis if product search finds results
                        if mongodb_results:
                            review_results = mongodb_service.analyze_product_reviews(
                                product_keywords)
                            mongodb_results.extend(review_results)

                    else:  # general
                        logger.info(
                            f"General intent, trying search_products first with keywords: '{product_keywords}'")
                        mongodb_results = mongodb_service.search_products(
                            product_keywords)
                        if not mongodb_results:
                            mongodb_results = mongodb_service.analyze_product_reviews(
                                product_keywords)
                else:
                    # Fallback: Use keyword-based detection (old method)
                    logger.info(
                        "Using fallback keyword-based intent detection")
                    query_lower = sanitized_question.lower()
                    is_review_query = any(keyword in query_lower for keyword in [
                        "most liked", "best rated", "highest rating", "popular",
                        "reviews", "rating", "likes", "favorite", "top"
                    ])

                    if is_review_query:
                        logger.info("Fallback: Detected review/rating query")
                        mongodb_results = mongodb_service.find_most_liked_product(
                            sanitized_question)
                        if not mongodb_results:
                            mongodb_results = mongodb_service.analyze_product_reviews(
                                sanitized_question)
                    else:
                        logger.info("Fallback: General product search")
                        mongodb_results = mongodb_service.search_products(
                            sanitized_question)
                        if mongodb_results:
                            review_results = mongodb_service.analyze_product_reviews(
                                sanitized_question)
                            mongodb_results.extend(review_results)

                all_chunks.extend(mongodb_results)
                logger.info(
                    f"✓ Found {len(mongodb_results)} results from MongoDB")
            except Exception as e:
                logger.warning(f"✗ MongoDB search failed: {str(e)}")

        # Sort chunks by score (highest first) and limit total results
        all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        chunks = all_chunks[:settings.max_retrieval_chunks]

        # Always proceed to LLM, even if no chunks found
        if not chunks:
            logger.info(
                "No relevant chunks found from any source - proceeding to LLM anyway")
        else:
            logger.info(f"Combined {len(chunks)} chunks from all sources")

        # Get conversation history if conversation_id is provided
        conversation_history = []
        logger.info(
            f"Conversation memory check - conversation_id: '{ask_request.conversation_id}', enabled: {settings.enable_conversation_memory}")
        if ask_request.conversation_id and settings.enable_conversation_memory and conversation_service:
            logger.info(
                f"Retrieving conversation history for conversation_id: '{ask_request.conversation_id}'")
            conversation_history = conversation_service.get_history(
                ask_request.conversation_id,
                max_messages=settings.max_conversation_history
            )
            if conversation_history:
                logger.info(
                    f"✓ Retrieved {len(conversation_history)} messages from conversation history")
                logger.info(
                    f"Conversation history preview: {[{'role': m.get('role'), 'content': m.get('content', '')[:50]} for m in conversation_history]}")
            else:
                logger.info(
                    f"No previous conversation history found for conversation_id: '{ask_request.conversation_id}' (this might be the first message)")
        elif not ask_request.conversation_id:
            logger.info(
                "No conversation_id provided - conversation memory disabled for this request")
        elif not settings.enable_conversation_memory:
            logger.warning(
                "Conversation memory is DISABLED - set ENABLE_CONVERSATION_MEMORY=true in .env")

        # Build prompt
        logger.info(f"Building prompt with {len(chunks)} chunks")
        if conversation_history:
            logger.info(
                f"Including {len(conversation_history)} previous messages in context")
        if bedrock_service:
            prompt = bedrock_service.build_prompt(
                sanitized_question, chunks, conversation_history)
        else:
            raise HTTPException(
                status_code=500, detail="BedrockService not initialized")

        # Generate answer using Bedrock
        logger.info("Calling AWS Bedrock LLM")
        try:
            answer = bedrock_service.generate_answer(prompt, max_tokens=1000)
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Bedrock LLM call failed: {error_msg}", exc_info=True)
            # Return detailed error message for debugging
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate answer: {error_msg}"
            )

        # Extract sources
        sources = extract_sources_from_chunks(chunks)

        # Store conversation history if conversation_id is provided
        if ask_request.conversation_id and settings.enable_conversation_memory and conversation_service:
            if conversation_service.enabled:
                # Add user message to history
                conversation_service.add_message(
                    ask_request.conversation_id,
                    role="user",
                    content=sanitized_question,
                    ttl_hours=settings.conversation_ttl_hours
                )
                # Add assistant response to history
                conversation_service.add_message(
                    ask_request.conversation_id,
                    role="assistant",
                    content=answer,
                    ttl_hours=settings.conversation_ttl_hours
                )
                logger.info(
                    f"✓ Stored conversation messages for conversation_id: {ask_request.conversation_id}")
            else:
                logger.warning(
                    f"✗ Cannot store conversation - ConversationService is disabled (check Redis connection)")

        # Cache the result
        if cache_service:
            cache_service.set(sanitized_question, answer, sources)

        # Calculate response time
        response_time = time.time() - start_time
        logger.info(
            f"Answer generated in {response_time:.2f}s with {len(sources)} sources")

        return AskResponse(
            answer=answer,
            sources=sources
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred"
        )


@router.post("/add-embedding", response_model=AddEmbeddingResponse)
async def add_embedding(
    request: Request,
    embedding_request: AddEmbeddingRequest,
    source: str = Query(...,
                        description="Source identifier (e.g., file path, URL)"),
    chunk_size: int = Query(
        1000, description="Chunk size for text splitting", ge=100, le=5000),
    overlap: int = Query(
        200, description="Overlap between chunks", ge=0, le=1000),
    _: None = Depends(verify_api_key)
):
    """
    Add embeddings to Qdrant via API.

    Accepts text content, generates embeddings, and stores them in Qdrant.
    Text is automatically chunked if it exceeds chunk_size.

    Returns:
        AddEmbeddingResponse with success status and number of chunks indexed
    """

    try:
        # Initialize Qdrant client
        qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=30.0
        )

        # Parse metadata if provided
        # Accepts both JSON string and plain text
        metadata_dict = None
        if embedding_request.metadata:
            try:
                # Try to parse as JSON first
                metadata_dict = json.loads(embedding_request.metadata)
            except json.JSONDecodeError:
                # If not valid JSON, treat as plain text description
                metadata_dict = {"description": embedding_request.metadata}
                logger.info(
                    f"Metadata provided as plain text, storing as 'description' field")

        # Chunk the text if needed
        text = embedding_request.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Text cannot be empty")

        # Simple chunking logic
        chunks = []
        if len(text) <= chunk_size:
            chunks = [text]
        else:
            start = 0
            while start < len(text):
                end = start + chunk_size

                # Try to break at sentence or line boundary
                if end < len(text):
                    newline_pos = text.rfind('\n', start, end)
                    if newline_pos != -1:
                        end = newline_pos + 1
                    else:
                        sentence_end = text.rfind('. ', start, end)
                        if sentence_end != -1:
                            end = sentence_end + 2

                chunk = text[start:end].strip()
                if chunk:
                    chunks.append(chunk)

                start = end - overlap

        if not chunks:
            raise HTTPException(
                status_code=400, detail="No valid chunks created from text")

        # Generate embeddings and prepare points
        points = []
        if not vector_db_service:
            raise HTTPException(
                status_code=500, detail="VectorDBService not initialized")

        for idx, chunk in enumerate(chunks):
            try:
                # Generate embedding
                embedding = vector_db_service.generate_embedding(chunk)

                # Create unique ID for this chunk
                chunk_id = f"{source}_{idx}"
                point_id = int(hashlib.md5(
                    chunk_id.encode()).hexdigest()[:8], 16)

                # Prepare payload
                payload = {
                    "text": chunk,
                    "source": source,
                    "chunk_id": chunk_id,
                    "file_path": source,
                    "chunk_index": idx,
                    "total_chunks": len(chunks)
                }

                # Add custom metadata if provided
                if metadata_dict:
                    payload.update(metadata_dict)

                # Create point
                point = PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
                points.append(point)

            except Exception as e:
                logger.error(f"Error processing chunk {idx}: {str(e)}")
                continue

        if not points:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate embeddings for any chunks"
            )

        # Upsert points to Qdrant
        try:
            qdrant_client.upsert(
                collection_name=settings.qdrant_collection_name,
                points=points
            )
            logger.info(
                f"Indexed {len(points)} chunks from source: {source}")

            return AddEmbeddingResponse(
                success=True,
                chunks_indexed=len(points),
                message=f"Successfully indexed {len(points)} chunk(s) from {source}"
            )

        except Exception as e:
            logger.error(f"Error storing embeddings in Qdrant: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to store embeddings: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error adding embedding: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while adding embeddings"
        )


@router.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": " AI Assistant API",
        "version": "1.0.0",
        "endpoints": {
            "ask": "/ask",
            "add-embedding": "/add-embedding",
            "health": "/health"
        }
    }
