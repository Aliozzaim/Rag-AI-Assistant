"""
Conversation memory service for storing and retrieving conversation history.
Uses Redis to store conversation context across multiple messages.
"""
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing conversation history and context."""

    def __init__(self):
        """Initialize Redis client for conversation storage."""
        logger.info(f"Initializing ConversationService")
        logger.info(f"Redis Host: {settings.redis_host}:{settings.redis_port}")

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
            logger.info("✓ Conversation memory enabled and connected")
        except Exception as e:
            logger.warning(f"✗ Conversation memory disabled: {str(e)}")
            logger.info("  Conversation history will not be stored")
            self.enabled = False
            self.redis_client = None

    def _get_conversation_key(self, conversation_id: str) -> str:
        """Generate Redis key for conversation."""
        return f"sparky:conversation:{conversation_id}"

    def get_history(self, conversation_id: str, max_messages: int = 10) -> List[Dict]:
        """
        Get conversation history for a conversation ID.

        Args:
            conversation_id: Unique conversation identifier
            max_messages: Maximum number of messages to retrieve (most recent)

        Returns:
            List of message dictionaries with 'role' and 'content'
        """
        if not self.enabled:
            logger.warning(
                f"ConversationService is disabled - cannot retrieve history for '{conversation_id}'")
            return []

        try:
            key = self._get_conversation_key(conversation_id)
            logger.debug(f"Looking up conversation history with key: {key}")
            history_json = self.redis_client.get(key)
            if history_json:
                history = json.loads(history_json)
                logger.info(
                    f"Found conversation history: {len(history)} total messages")
                # Return most recent messages (limit to max_messages)
                result = history[-max_messages:] if len(
                    history) > max_messages else history
                logger.info(
                    f"Returning {len(result)} messages (max: {max_messages})")
                return result
            else:
                logger.info(
                    f"No conversation history found in Redis for key: {key}")
            return []
        except Exception as e:
            logger.error(
                f"Failed to retrieve conversation history for '{conversation_id}': {str(e)}", exc_info=True)
            return []

    def add_message(self, conversation_id: str, role: str, content: str, ttl_hours: int = 24):
        """
        Add a message to conversation history.

        Args:
            conversation_id: Unique conversation identifier
            role: Message role ('user' or 'assistant')
            content: Message content
            ttl_hours: Time to live in hours (default: 24 hours)
        """
        if not self.enabled:
            logger.warning(
                f"Cannot store message - ConversationService is disabled (Redis not connected)")
            return

        try:
            key = self._get_conversation_key(conversation_id)

            # Get existing history
            history_json = self.redis_client.get(key)
            history = json.loads(history_json) if history_json else []

            # Add new message
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }
            history.append(message)

            # Limit history size (keep last 50 messages max)
            if len(history) > 50:
                history = history[-50:]

            # Store updated history with TTL
            ttl_seconds = ttl_hours * 3600
            self.redis_client.setex(
                key,
                ttl_seconds,
                json.dumps(history)
            )
            logger.debug(
                f"Added {role} message to conversation {conversation_id}")
        except Exception as e:
            logger.warning(f"Failed to store conversation message: {str(e)}")

    def clear_history(self, conversation_id: str):
        """
        Clear conversation history for a conversation ID.

        Args:
            conversation_id: Unique conversation identifier
        """
        if not self.enabled:
            return

        try:
            key = self._get_conversation_key(conversation_id)
            self.redis_client.delete(key)
            logger.info(f"Cleared conversation history for {conversation_id}")
        except Exception as e:
            logger.warning(f"Failed to clear conversation history: {str(e)}")

    def health_check(self) -> bool:
        """
        Check if conversation service is healthy.

        Returns:
            True if healthy, False otherwise
        """
        if not self.enabled:
            return False

        try:
            result = self.redis_client.ping()
            return result
        except Exception as e:
            logger.error(f"Conversation service health check failed: {str(e)}")
            return False
