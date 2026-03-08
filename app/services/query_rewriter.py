"""
Query rewriting service to improve search results using LLM.
Uses AWS Bedrock LLM to rewrite queries for better semantic search.
"""
import logging
import json
from typing import Optional, Dict
from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
BedrockService = None


class QueryRewriter:
    """Service for rewriting queries to improve search results."""

    def __init__(self):
        """Initialize query rewriter."""
        self.bedrock_service = None
        if settings.enable_llm_query_rewriting:
            try:
                # Lazy import to avoid circular dependencies
                from app.services.bedrock_service import BedrockService
                self.bedrock_service = BedrockService()
                logger.info("✓ LLM query rewriting enabled")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize BedrockService for query rewriting: {e}")
                logger.info("  Query rewriting will be disabled")

    def rewrite_query(self, query: str, use_llm: bool = False) -> str:
        """
        Rewrite query to improve search results using LLM.

        Args:
            query: Original user query
            use_llm: If True, use LLM for query rewriting

        Returns:
            Rewritten query optimized for semantic search, or original if LLM rewriting fails/disabled
        """
        # Only use LLM rewriting if enabled
        if use_llm and self.bedrock_service:
            try:
                rewritten = self._llm_rewrite(query)
                if rewritten and rewritten != query:
                    logger.info(
                        f"LLM query rewrite: '{query}' -> '{rewritten}'")
                    return rewritten
                else:
                    logger.debug(
                        f"LLM rewriting returned no changes for: '{query}'")
            except Exception as e:
                logger.warning(
                    f"LLM query rewriting failed: {e}, using original query")

        # If LLM rewriting is disabled or failed, return original query
        logger.debug(
            f"Query rewriting skipped, using original query: '{query}'")
        return query

    def _llm_rewrite(self, query: str) -> Optional[str]:
        """
        Use LLM to rewrite query for better semantic search.

        Args:
            query: Query to rewrite

        Returns:
            Rewritten query or None if rewriting fails
        """
        if not self.bedrock_service:
            return None

        prompt = f"""You are a query rewriting assistant. Your task is to rewrite user queries to improve semantic search results.

Rules:
1. Fix typos and spelling errors
2. Expand abbreviations 
3. Add relevant synonyms and related terms
4. Keep the original intent and meaning
5. Make the query more specific and search-friendly
6. Do NOT change the core question or add unrelated information

Original query: {query}

Rewritten query (just the query, no explanation):"""

        try:
            rewritten = self.bedrock_service.generate_answer(
                prompt, max_tokens=500)
            # Clean up the response (remove quotes, extra whitespace)
            rewritten = rewritten.strip().strip('"').strip("'").strip()
            return rewritten if rewritten else None
        except Exception as e:
            logger.warning(f"LLM query rewriting failed: {e}")
            return None

    def generate_query_variations(self, query: str) -> list[str]:
        """
        Generate multiple query variations for better recall using LLM.

        Args:
            query: Original query

        Returns:
            List of query variations (currently just returns original if LLM not enabled)
        """
        variations = [query]  # Always include original

        # If LLM rewriting is enabled, add rewritten version
        if self.bedrock_service:
            try:
                rewritten = self._llm_rewrite(query)
                if rewritten and rewritten != query:
                    variations.append(rewritten)
            except Exception as e:
                logger.debug(f"Failed to generate LLM variation: {e}")

        return variations

    def extract_mongodb_intent(self, query: str) -> Optional[Dict[str, str]]:
        """
        Extract intent and product keywords from query for MongoDB search.
        Uses LLM to understand user intent and extract relevant product information.

        Args:
            query: User query

        Returns:
            Dictionary with 'intent' and 'product_keywords', or None if extraction fails
            Intent can be: 'search_products', 'find_most_liked', 'analyze_reviews', 'general'
        """
        if not self.bedrock_service:
            # Fallback to simple extraction if LLM not available
            return self._simple_intent_extraction(query)

        prompt = f"""You are an intent extraction assistant for a product database search system.

Analyze the following user query and extract:
1. The user's intent (what they want to do)
2. The product name/keywords they're searching for

Intent options:
- "find_most_liked": User wants to find the most liked/popular/best rated product version
- "analyze_reviews": User wants to see reviews or ratings for products
- "search_products": User wants to search for products by name/brand
- "general": General product inquiry

Product keywords: Extract the actual product name, brand, or model (remove question words, stop words, and intent phrases)

Examples:
Query: "what is most liked iPhone ?"
Intent: find_most_liked
Product keywords: iPhone

Query: "show me reviews for Samsung Galaxy"
Intent: analyze_reviews
Product keywords: Samsung Galaxy

Query: "iPhone 15"
Intent: search_products
Product keywords: iPhone 15

Query: "best rated phone"
Intent: find_most_liked
Product keywords: phone

User query: {query}

Respond ONLY with valid JSON in this exact format (no markdown, no explanation):
{{
  "intent": "find_most_liked",
  "product_keywords": "iPhone"
}}"""

        try:
            response = self.bedrock_service.generate_answer(
                prompt, max_tokens=200)
            
            # Clean up response - remove markdown code blocks if present
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            # Parse JSON response
            result = json.loads(response)
            
            # Validate and normalize
            intent = result.get("intent", "general").lower()
            product_keywords = result.get("product_keywords", "").strip()
            
            # Normalize intent values
            valid_intents = ["find_most_liked", "analyze_reviews", "search_products", "general"]
            if intent not in valid_intents:
                # Map similar intents
                if "most" in intent or "best" in intent or "popular" in intent or "liked" in intent:
                    intent = "find_most_liked"
                elif "review" in intent or "rating" in intent:
                    intent = "analyze_reviews"
                elif "search" in intent or "find" in intent:
                    intent = "search_products"
                else:
                    intent = "general"
            
            if not product_keywords:
                # Fallback to simple extraction
                return self._simple_intent_extraction(query)
            
            logger.info(
                f"Extracted intent: '{intent}', product_keywords: '{product_keywords}' from query: '{query}'")
            
            return {
                "intent": intent,
                "product_keywords": product_keywords
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM intent extraction JSON: {e}")
            logger.debug(f"LLM response was: {response[:200]}")
            return self._simple_intent_extraction(query)
        except Exception as e:
            logger.warning(f"LLM intent extraction failed: {e}, using fallback")
            return self._simple_intent_extraction(query)

    def _simple_intent_extraction(self, query: str) -> Dict[str, str]:
        """
        Simple fallback intent extraction without LLM.
        Uses keyword matching to determine intent and extract product keywords.

        Args:
            query: User query

        Returns:
            Dictionary with 'intent' and 'product_keywords'
        """
        query_lower = query.lower()
        
        # Determine intent based on keywords
        if any(keyword in query_lower for keyword in [
            "most liked", "best rated", "highest rating", "most popular",
            "top", "favorite", "best"
        ]):
            intent = "find_most_liked"
        elif any(keyword in query_lower for keyword in [
            "reviews", "rating", "ratings", "review"
        ]):
            intent = "analyze_reviews"
        else:
            intent = "search_products"
        
        # Simple keyword extraction (remove common question words)
        import re
        cleaned = re.sub(r'\b(what|which|how|where|when|why|is|are|the|a|an|most|best|liked|rated|popular|top|favorite)\b', 
                        '', query_lower, flags=re.IGNORECASE)
        product_keywords = ' '.join(cleaned.split()).strip()
        
        # If we got nothing, use original query
        if not product_keywords:
            product_keywords = query.strip()
        
        return {
            "intent": intent,
            "product_keywords": product_keywords
        }
