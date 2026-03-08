"""
Caching service for storing and retrieving answers.
Uses Redis for distributed caching.
"""
import logging
import json
import hashlib
from typing import Optional
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Service for caching answers to improve performance."""
    
    def __init__(self):
        """Initialize Redis client."""
        logger.info(f"Initializing CacheService")
        logger.info(f"Redis Host: {settings.redis_host}:{settings.redis_port}")
        logger.info(f"Redis DB: {settings.redis_db}")
        
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password,
                db=settings.redis_db,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            self.enabled = True
            logger.info("✓ Redis cache enabled and connected")
        except Exception as e:
            logger.warning(f"✗ Redis cache disabled: {str(e)}")
            logger.info("  Cache will be disabled - answers will not be cached")
            self.enabled = False
            self.redis_client = None
    
    def _generate_cache_key(self, question: str) -> str:
        """
        Generate a cache key from the question.
        
        Args:
            question: User question
            
        Returns:
            Cache key string
        """
        # Normalize question (lowercase, strip whitespace)
        normalized = question.lower().strip()
        # Generate hash
        hash_obj = hashlib.md5(normalized.encode())
        return f":answer:{hash_obj.hexdigest()}"
    
    def get(self, question: str) -> Optional[dict]:
        """
        Retrieve cached answer for a question.
        
        Args:
            question: User question
            
        Returns:
            Cached answer dict with 'answer' and 'sources', or None if not found
        """
        if not self.enabled:
            return None
        
        try:
            cache_key = self._generate_cache_key(question)
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
            return None
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {str(e)}")
            return None
    
    def set(self, question: str, answer: str, sources: list, ttl: int = None):
        """
        Cache an answer for a question.
        
        Args:
            question: User question
            answer: Generated answer
            sources: List of source files
            ttl: Time to live in seconds (uses default from settings if None)
        """
        if not self.enabled:
            return
        
        try:
            cache_key = self._generate_cache_key(question)
            cache_data = {
                "answer": answer,
                "sources": sources
            }
            ttl = ttl or settings.cache_ttl_seconds
            self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(cache_data)
            )
            logger.info(f"Cached answer for question (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Cache storage failed: {str(e)}")
    
    def health_check(self) -> bool:
        """
        Check if cache service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        if not self.enabled:
            logger.info("Cache health check: Disabled (skipped)")
            return False
        
        logger.info(f"Checking Redis cache health ({settings.redis_host}:{settings.redis_port})")
        try:
            result = self.redis_client.ping()
            logger.info("✓ Redis cache health check passed")
            return result
        except Exception as e:
            logger.error(f"✗ Redis cache health check failed: {str(e)}")
            return False
