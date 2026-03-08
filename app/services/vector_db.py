"""
Vector database service for retrieving relevant knowledge base chunks.
Uses Qdrant for vector similarity search.
"""
import logging
from typing import List, Dict, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from qdrant_client.http.models import Range
from app.services.embedding_service import EmbeddingService
from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorDBService:
    """Service for interacting with Qdrant vector database."""

    def __init__(self):
        """Initialize Qdrant client and embedding service."""
        logger.info(f"Initializing VectorDBService")
        logger.info(f"Qdrant URL: {settings.qdrant_url}")
        logger.info(f"Collection: {settings.qdrant_collection_name}")

        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=10.0
        )
        self.collection_name = settings.qdrant_collection_name

        # Initialize embedding service based on provider
        logger.info(f"Embedding Provider: {settings.embedding_provider}")
        if settings.embedding_provider == "bedrock":
            logger.info(f"Initializing Bedrock embedding service")
            logger.info(f"  Model: {settings.embedding_model}")
            logger.info(f"  Dimension: {settings.embedding_dimension}")
            logger.info(f"  Region: {settings.aws_region}")
            self.embedding_service = EmbeddingService(
                provider="bedrock",
                region=settings.aws_region,
                aws_profile=settings.aws_profile,
                access_key_id=settings.aws_access_key_id,
                secret_access_key=settings.aws_secret_access_key,
                model_id=settings.embedding_model,
                dimension=settings.embedding_dimension
            )
            logger.info(f"✓ Bedrock embedding service initialized")
        elif settings.embedding_provider == "local":
            logger.info(f"Initializing local embedding service")
            logger.info(f"  Model: {settings.embedding_model}")
            self.embedding_service = EmbeddingService(
                provider="local",
                model_name=settings.embedding_model
            )
            logger.info(f"✓ Local embedding service initialized")
        elif settings.embedding_provider == "openai":
            logger.info(f"Initializing OpenAI embedding service")
            logger.info(f"  Model: {settings.embedding_model}")
            self.embedding_service = EmbeddingService(
                provider="openai",
                api_key=settings.openai_api_key,
                model=settings.embedding_model
            )
            logger.info(f"✓ OpenAI embedding service initialized")
        else:
            raise ValueError(
                f"Unsupported embedding provider: {settings.embedding_provider}")

        logger.info(f"✓ VectorDBService initialized successfully")

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for the given text.

        Args:
            text: Text to generate embedding for

        Returns:
            List of float values representing the embedding vector

        Raises:
            Exception: If embedding generation fails
        """
        logger.debug(f"Generating embedding for text ({len(text)} chars)")
        try:
            embedding = self.embedding_service.generate_embedding(text)
            logger.debug(
                f"✓ Generated embedding with {len(embedding)} dimensions")
            return embedding
        except Exception as e:
            logger.error(f"✗ Failed to generate embedding: {str(e)}")
            raise

    def _retrieve_adjacent_chunks(
        self,
        source: str,
        chunk_index: int,
        total_chunks: int,
        window: int = 1
    ) -> List[Dict]:
        """
        Retrieve adjacent chunks from the same document for better context.

        Args:
            source: Source identifier (document path)
            chunk_index: Index of the central chunk
            total_chunks: Total number of chunks in the document
            window: Number of chunks before/after to retrieve

        Returns:
            List of adjacent chunks with metadata
        """
        try:
            # Calculate range bounds
            start_idx = max(0, chunk_index - window)
            end_idx = min(total_chunks - 1, chunk_index + window)

            # Create filter for adjacent chunks
            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="source", match=MatchValue(value=source)),
                    FieldCondition(
                        key="chunk_index",
                        range=Range(gte=start_idx, lte=end_idx)
                    )
                ]
            )

            # Use scroll to retrieve all matching chunks
            # Note: scroll doesn't use vector similarity, just filtering
            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=filter_condition,
                limit=end_idx - start_idx + 1,
                with_payload=True,
                with_vectors=False
            )

            adjacent_chunks = []
            for result in results:
                adjacent_chunks.append({
                    "id": result.id,
                    "score": 0.0,  # No similarity score for filtered results
                    "payload": result.payload or {},
                    "is_adjacent": True  # Mark as adjacent chunk
                })

            logger.debug(
                f"Retrieved {len(adjacent_chunks)} adjacent chunks for source={source}, "
                f"chunk_index={chunk_index} (range: {start_idx}-{end_idx})"
            )
            return adjacent_chunks

        except Exception as e:
            logger.warning(
                f"Failed to retrieve adjacent chunks for {source}:{chunk_index}: {str(e)}")
            return []

    def search_similar_chunks(
        self,
        query_embedding: List[float],
        limit: int = 5,
        score_threshold: float = 0.3,
        include_adjacent: bool = True,
        adjacent_window: int = 1
    ) -> List[Dict]:
        """
        Search for similar chunks in the vector database.
        Optionally includes adjacent chunks from the same document for better context.

        Args:
            query_embedding: Embedding vector of the query
            limit: Maximum number of primary results to return
            score_threshold: Minimum similarity score threshold
            include_adjacent: If True, also retrieve adjacent chunks (±window) from same document
            adjacent_window: Number of chunks before/after to retrieve (default: 1)

        Returns:
            List of similar chunks with metadata (may include adjacent chunks)

        Raises:
            Exception: If search fails
        """
        logger.info(f"Searching Qdrant collection '{self.collection_name}'")
        logger.info(f"  Limit: {limit}, Score threshold: {score_threshold}")
        if include_adjacent:
            logger.info(
                f"  Adjacent chunks: enabled (window: ±{adjacent_window})")
        logger.debug(f"  Query embedding dimension: {len(query_embedding)}")

        try:
            # Use query_points() method for vector similarity search
            # query_points() accepts list[float] directly as a dense vector for nearest search
            query_result = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,  # Direct vector list for nearest search
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False
            )
            results = query_result.points

            # Log search results for debugging
            if results:
                scores = [r.score for r in results]
                logger.info(
                    f"  Search returned {len(results)} results with scores: {[f'{s:.3f}' for s in scores]}")
                logger.info(
                    f"  Score range: {min(scores):.3f} - {max(scores):.3f}")
            else:
                logger.warning(
                    f"  No results returned (all below threshold {score_threshold})")
                # Try a lower threshold search to see what we're missing
                logger.info(
                    f"  Attempting search with lower threshold (0.0) to check available results...")
                fallback_result = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_embedding,
                    limit=limit,
                    score_threshold=0.0,  # No threshold
                    with_payload=True,
                    with_vectors=False
                )
                fallback_results = fallback_result.points
                if fallback_results:
                    fallback_scores = [r.score for r in fallback_results]
                    logger.info(
                        f"  Found {len(fallback_results)} results with lower threshold")
                    logger.info(
                        f"  Top scores without threshold: {[f'{s:.3f}' for s in fallback_scores[:5]]}")
                    logger.info(
                        f"  Consider lowering SCORE_THRESHOLD from {score_threshold} to {min(fallback_scores):.3f} or lower")

            chunks = []
            seen_chunk_ids = set()  # Track chunks we've already added

            # Process primary search results
            for result in results:
                chunk_id = result.id
                payload = result.payload or {}
                source = payload.get("source", "")
                chunk_index = payload.get("chunk_index")
                total_chunks = payload.get("total_chunks")

                # Add primary chunk
                chunks.append({
                    "id": chunk_id,
                    "score": result.score,
                    "payload": payload,
                    "is_adjacent": False
                })
                seen_chunk_ids.add(chunk_id)

                # Retrieve adjacent chunks if enabled and we have the necessary metadata
                if include_adjacent and source and chunk_index is not None and total_chunks:
                    adjacent = self._retrieve_adjacent_chunks(
                        source=source,
                        chunk_index=chunk_index,
                        total_chunks=total_chunks,
                        window=adjacent_window
                    )

                    # Add adjacent chunks that we haven't seen yet
                    for adj_chunk in adjacent:
                        if adj_chunk["id"] not in seen_chunk_ids:
                            chunks.append(adj_chunk)
                            seen_chunk_ids.add(adj_chunk["id"])

            logger.info(f"✓ Retrieved {len(chunks)} chunks from Qdrant")
            if chunks:
                primary_count = sum(
                    1 for c in chunks if not c.get("is_adjacent", False))
                adjacent_count = len(chunks) - primary_count
                logger.info(
                    f"  Primary chunks: {primary_count}, Adjacent chunks: {adjacent_count}")
                logger.debug(f"  Top score: {chunks[0].get('score', 0):.4f}")

            return chunks

        except Exception as e:
            logger.error(f"✗ Qdrant search failed: {str(e)}")
            raise

    def health_check(self) -> bool:
        """
        Check if the Qdrant connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        logger.info(
            f"Checking Qdrant health (collection: {self.collection_name})")
        try:
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            is_healthy = self.collection_name in collection_names

            if is_healthy:
                logger.info(
                    f"✓ Qdrant health check passed (collection exists)")
            else:
                logger.warning(
                    f"✗ Qdrant health check failed: Collection '{self.collection_name}' not found")
                logger.info(f"  Available collections: {collection_names}")

            return is_healthy
        except Exception as e:
            logger.error(f"✗ Qdrant health check failed: {str(e)}")
            return False
