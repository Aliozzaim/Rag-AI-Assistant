"""
MongoDB service for querying product data and reviews from product_scraper_api database.
Supports searching products and analyzing reviews to answer questions about products.
"""
import logging
import re
from typing import List, Dict, Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from bson import ObjectId
from bson.errors import InvalidId
from app.core.config import settings

logger = logging.getLogger(__name__)


class MongoDBService:
    """Service for querying MongoDB product database."""

    def __init__(self):
        """Initialize MongoDB service with configuration."""
        logger.info(f"Initializing MongoDBService")
        logger.info(
            f"MongoDB URI: {settings.mongodb_uri[:30]}..." if settings.mongodb_uri else "Not configured")
        logger.info(f"Enabled: {settings.mongodb_enabled}")

        self.mongodb_uri = settings.mongodb_uri
        self.enabled = settings.mongodb_enabled
        self.database_name = settings.mongodb_database_name
        self.products_collection = settings.mongodb_products_collection
        self.reviews_collection = settings.mongodb_reviews_collection
        self.max_results = settings.mongodb_max_results
        self.timeout = settings.mongodb_timeout

        self.client: Optional[MongoClient] = None

        if self.enabled and self.mongodb_uri:
            try:
                self.client = MongoClient(
                    self.mongodb_uri,
                    serverSelectionTimeoutMS=self.timeout * 1000,
                    connectTimeoutMS=self.timeout * 1000,
                    socketTimeoutMS=self.timeout * 1000
                )
                # Test connection
                self.client.admin.command('ping')
                logger.info("✓ MongoDBService initialized and connected")
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                logger.warning(f"✗ MongoDB connection failed: {str(e)}")
                logger.info("  MongoDB queries will be disabled")
                self.enabled = False
                self.client = None
            except Exception as e:
                logger.error(f"✗ MongoDB initialization error: {str(e)}")
                self.enabled = False
                self.client = None
        else:
            logger.info("✓ MongoDBService initialized (disabled)")
            self.enabled = False

    def _is_valid_objectid(self, value: str) -> bool:
        """Check if string is a valid MongoDB ObjectId format."""
        try:
            ObjectId(value)
            return len(value) == 24 and all(c in '0123456789abcdef' for c in value.lower())
        except (InvalidId, TypeError):
            return False

    def _extract_keywords_from_url(self, url: str) -> str:
        """Extract potential product keywords from marketplace URL."""
        # Common patterns in marketplace URLs
        # Example: https://www.hepsiburada.com/iphone-14-pro-max-p-HBV00001234567
        # Extract words between slashes and hyphens
        keywords = re.findall(r'[a-zA-Z]+', url.lower())
        return ' '.join(keywords)

    def _extract_product_keywords(self, query: str) -> str:
        """
        Extract product name/keywords from a natural language query.
        This is now a fallback method - prefer using QueryRewriter.extract_mongodb_intent()
        which uses LLM for better extraction.

        Examples:
        - "what is most liked iPhone ?" -> "iPhone"
        - "best rated Samsung Galaxy" -> "Samsung Galaxy"
        - "most popular phone" -> "phone"
        """
        # Remove common question words and phrases
        question_patterns = [
            r'what\s+is\s+',
            r'which\s+is\s+',
            r'what\s+are\s+',
            r'which\s+are\s+',
            r'what\s+',
            r'which\s+',
            r'how\s+',
            r'where\s+',
            r'when\s+',
            r'why\s+',
            r'most\s+liked\s+',
            r'most\s+popular\s+',
            r'best\s+rated\s+',
            r'best\s+',
            r'highest\s+rated\s+',
            r'top\s+',
            r'reviews?\s+of\s+',
            r'reviews?\s+for\s+',
            r'rating\s+of\s+',
            r'rating\s+for\s+',
            r'\?',
            r'\.',
        ]

        cleaned_query = query.lower()
        for pattern in question_patterns:
            cleaned_query = re.sub(
                pattern, ' ', cleaned_query, flags=re.IGNORECASE)

        # Remove extra whitespace and split into words
        words = cleaned_query.strip().split()

        # Filter out common stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this',
            'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
            'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'her', 'its',
            'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs'
        }

        # Keep only meaningful words (not stop words, at least 2 characters)
        keywords = [w for w in words if w not in stop_words and len(w) >= 2]

        # Return the cleaned keywords as a string
        result = ' '.join(keywords).strip()

        # If we got nothing meaningful, return original query (maybe it's already a product name)
        if not result:
            return query.strip()

        return result

    def search_products(self, query: str) -> List[Dict]:
        """
        Search for products by ID, keywords, or marketplace URLs.

        Args:
            query: Search query string (e.g., "iPhone", "Samsung Galaxy", ObjectId)

        Returns:
            List of product results with metadata
        """
        if not self.enabled or not self.client:
            return []

        try:
            # Use query directly if it looks like a clean product name/keyword
            # Otherwise extract keywords (fallback for when LLM extraction isn't used)
            # Check if query is already clean (no question words, short, etc.)
            if len(query.split()) <= 5 and not any(word in query.lower() for word in ['what', 'which', 'how', 'where', 'when', 'why', 'most', 'best']):
                product_keywords = query
                logger.debug(
                    f"Using query directly as product keywords: '{product_keywords}'")
            else:
                product_keywords = self._extract_product_keywords(query)
                logger.debug(
                    f"Extracted product keywords from '{query}': '{product_keywords}'")

            db = self.client[self.database_name]
            products_col = db[self.products_collection]

            # Build search query with multiple strategies
            search_conditions = []

            # 1. Search by ObjectId if query looks like one
            if self._is_valid_objectid(query):
                try:
                    search_conditions.append({"_id": ObjectId(query)})
                except (InvalidId, ValueError):
                    pass

            # 2. Search by product name (most important field!) - use extracted keywords
            search_conditions.append(
                {"name": {"$regex": product_keywords, "$options": "i"}})

            # 3. Search by brand - use extracted keywords
            search_conditions.append(
                {"brand": {"$regex": product_keywords, "$options": "i"}})

            # 4. Search by akakce_id (if it's numeric)
            if query.isdigit():
                search_conditions.append({"akakce_id": query})

            # 5. Search in marketplace URLs (hepsiburada, n11, trendyol)
            # URLs often contain product names - use extracted keywords
            search_conditions.append({
                "$or": [
                    {"marketplaceOffers.hepsiburada": {
                        "$regex": product_keywords, "$options": "i"}},
                    {"marketplaceOffers.n11": {
                        "$regex": product_keywords, "$options": "i"}},
                    {"marketplaceOffers.trendyol": {
                        "$regex": product_keywords, "$options": "i"}},
                ]
            })

            search_query = {"$or": search_conditions} if len(
                search_conditions) > 1 else search_conditions[0]

            products = list(products_col.find(
                search_query).limit(self.max_results))

            results = []
            for product in products:
                product_id = str(product.get(
                    "_id", product.get("productId", "")))
                marketplace_offers = product.get("marketplaceOffers", {})

                # Extract product info
                product_name = product.get("name", "Unknown Product")
                brand = product.get("brand", "")
                akakce_id = product.get("akakce_id", "")

                product_info = f"Product: {product_name}"
                if brand:
                    product_info += f" ({brand})"
                product_info += f"\nProduct ID: {product_id}"
                if akakce_id:
                    product_info += f"\nAkakce ID: {akakce_id}"

                # Add marketplace offers info
                if marketplace_offers:
                    hepsiburada_offers = marketplace_offers.get(
                        "hepsiburada", [])
                    n11_offers = marketplace_offers.get("n11", [])
                    trendyol_offers = marketplace_offers.get("trendyol", [])

                    total_offers = len(hepsiburada_offers) + \
                        len(n11_offers) + len(trendyol_offers)
                    if total_offers > 0:
                        product_info += f"\nMarketplace offers: {len(hepsiburada_offers)} Hepsiburada, {len(n11_offers)} n11, {len(trendyol_offers)} Trendyol"

                        # Add price info if available
                        price_info = product.get("price", {})
                        if price_info:
                            price_count = price_info.get("priceCount", 0)
                            if price_count > 0:
                                product_info += f"\nPrice tracking: {price_count} price points"

                # Add rating info if available
                rating_info = product.get("rating", {})
                if rating_info:
                    product_info += f"\nRating data available"

                results.append({
                    "id": f"mongodb_product_{product_id}",
                    "score": 0.3,  # Default score for product search
                    "payload": {
                        "text": product_info,
                        "source": f"mongodb://{self.database_name}/{self.products_collection}",
                        "chunk_id": product_id,
                        "type": "product",
                        "product_id": product_id,
                        "marketplace_offers": marketplace_offers
                    }
                })

            logger.info(f"Found {len(results)} products from MongoDB")
            return results

        except Exception as e:
            logger.error(f"MongoDB product search failed: {str(e)}")
            return []

    def analyze_product_reviews(self, product_query: str) -> List[Dict]:
        """
        Analyze reviews for products matching the query.
        Finds products, aggregates their reviews, and returns analysis.

        Args:
            product_query: Product search query (e.g., "iPhone")

        Returns:
            List of review analysis results
        """
        if not self.enabled or not self.client:
            return []

        try:
            # Extract product keywords from natural language query
            product_keywords = self._extract_product_keywords(product_query)
            logger.debug(
                f"Extracted product keywords from '{product_query}': '{product_keywords}'")

            db = self.client[self.database_name]
            products_col = db[self.products_collection]
            reviews_col = db[self.reviews_collection]

            # Build search query with multiple strategies
            search_conditions = []

            # 1. Search by ObjectId if query looks like one
            if self._is_valid_objectid(product_query):
                try:
                    search_conditions.append({"_id": ObjectId(product_query)})
                except (InvalidId, ValueError):
                    pass

            # 2. Search by product name (most important!) - use extracted keywords
            search_conditions.append(
                {"name": {"$regex": product_keywords, "$options": "i"}})

            # 3. Search by brand - use extracted keywords
            search_conditions.append(
                {"brand": {"$regex": product_keywords, "$options": "i"}})

            # 4. Search by akakce_id (if numeric)
            if product_query.isdigit():
                search_conditions.append({"akakce_id": product_query})

            # 5. Search in marketplace URLs - use extracted keywords
            search_conditions.append({
                "$or": [
                    {"marketplaceOffers.hepsiburada": {
                        "$regex": product_keywords, "$options": "i"}},
                    {"marketplaceOffers.n11": {
                        "$regex": product_keywords, "$options": "i"}},
                    {"marketplaceOffers.trendyol": {
                        "$regex": product_keywords, "$options": "i"}},
                ]
            })

            search_query = {"$or": search_conditions} if len(
                search_conditions) > 1 else search_conditions[0]

            products = list(products_col.find(
                search_query).limit(self.max_results))

            if not products:
                logger.info(f"No products found matching '{product_query}'")
                return []

            results = []

            # For each product, analyze its reviews
            for product in products:
                product_id = str(product.get(
                    "_id", product.get("productId", "")))

                # Find reviews for this product
                # Reviews are stored in marketplace_reviews collection with productId field (as string)
                # productId in reviews matches the _id (ObjectId) of the product
                product_reviews = list(reviews_col.find(
                    {"productId": product_id}
                ).limit(100))  # Limit reviews per product for performance

                if not product_reviews:
                    continue

                # Aggregate review statistics
                # Each review document has aggregated rating and reviewCount at document level
                # Plus individual reviews in the reviews array
                total_reviews = 0
                ratings = []
                total_likes = 0
                verified_purchases = 0
                marketplace_ratings = {}  # Track ratings per marketplace

                for review_doc in product_reviews:
                    # Get aggregated rating from document level
                    doc_rating = review_doc.get("rating")
                    doc_review_count = review_doc.get("reviewCount", 0)
                    marketplace = review_doc.get("marketplace", "unknown")

                    if doc_rating and doc_review_count:
                        marketplace_ratings[marketplace] = {
                            "rating": doc_rating,
                            "count": doc_review_count
                        }

                    # Process individual reviews in the reviews array
                    reviews_list = review_doc.get("reviews", [])
                    if isinstance(reviews_list, list):
                        total_reviews += len(reviews_list)
                        for r in reviews_list:
                            rating = r.get("rating")
                            if rating:
                                ratings.append(rating)
                            total_likes += r.get("likesCount", 0)
                            if r.get("isPurchaseVerified"):
                                verified_purchases += 1
                    elif doc_review_count:
                        # If no reviews array but has reviewCount, use document-level rating
                        total_reviews += doc_review_count
                        if doc_rating:
                            # Approximate individual ratings from aggregated rating
                            for _ in range(min(doc_review_count, 10)):  # Limit approximation
                                ratings.append(round(doc_rating))

                # Calculate statistics
                avg_rating = sum(ratings) / len(ratings) if ratings else 0
                # Use document-level aggregated rating if available and better
                if marketplace_ratings:
                    aggregated_avg = sum(m["rating"] * m["count"] for m in marketplace_ratings.values()) / \
                        sum(m["count"] for m in marketplace_ratings.values())
                    if aggregated_avg > 0:
                        avg_rating = aggregated_avg

                rating_distribution = {}
                for rating in ratings:
                    rating_distribution[rating] = rating_distribution.get(
                        rating, 0) + 1

                # Find most liked reviews
                top_reviews = []
                for review in product_reviews:
                    reviews_list = review.get("reviews", [])
                    if isinstance(reviews_list, list):
                        for r in reviews_list:
                            likes = r.get("likesCount", 0)
                            if likes > 0:
                                top_reviews.append({
                                    "rating": r.get("rating"),
                                    "likes": likes,
                                    # Truncate long reviews
                                    "content": r.get("content", "")[:200],
                                    "author": r.get("author", ""),
                                    "marketplace": review.get("marketplace", "")
                                })

                # Sort by likes
                top_reviews.sort(key=lambda x: x["likes"], reverse=True)
                top_reviews = top_reviews[:5]  # Top 5 most liked reviews

                # Get product name for better context
                product_name = product.get("name", "Unknown Product")
                brand = product.get("brand", "")

                # Build analysis text
                analysis_text = f"Product Analysis: {product_name}"
                if brand:
                    analysis_text += f" ({brand})"
                analysis_text += f"\nProduct ID: {product_id}\n"
                analysis_text += f"Total Reviews: {total_reviews}\n"
                analysis_text += f"Average Rating: {avg_rating:.2f}/5.0\n"

                # Add marketplace-specific ratings if available
                if marketplace_ratings:
                    analysis_text += "\nRatings by Marketplace:\n"
                    for marketplace, data in marketplace_ratings.items():
                        analysis_text += f"  {marketplace}: {data['rating']:.2f}/5.0 ({data['count']} reviews)\n"

                analysis_text += f"Total Likes: {total_likes}\n"
                analysis_text += f"Verified Purchases: {verified_purchases}\n"
                if rating_distribution:
                    analysis_text += f"Rating Distribution: {dict(sorted(rating_distribution.items()))}\n"

                if top_reviews:
                    analysis_text += "\nTop Liked Reviews:\n"
                    for idx, r in enumerate(top_reviews, 1):
                        analysis_text += f"{idx}. Rating: {r['rating']}/5, Likes: {r['likes']}, "
                        analysis_text += f"Marketplace: {r['marketplace']}\n"
                        analysis_text += f"   Review: {r['content']}\n"

                results.append({
                    "id": f"mongodb_review_{product_id}",
                    # Higher score for highly rated products
                    "score": 0.9 if avg_rating >= 4.0 else 0.7,
                    "payload": {
                        "text": analysis_text,
                        "source": f"mongodb://{self.database_name}/{self.reviews_collection}",
                        "chunk_id": product_id,
                        "type": "product_review_analysis",
                        "product_id": product_id,
                        "total_reviews": total_reviews,
                        "average_rating": avg_rating,
                        "total_likes": total_likes,
                        "verified_purchases": verified_purchases,
                        "rating_distribution": rating_distribution
                    }
                })

            logger.info(
                f"Analyzed reviews for {len(results)} products from MongoDB")
            return results

        except Exception as e:
            logger.error(f"MongoDB review analysis failed: {str(e)}")
            return []

    def find_most_liked_product(self, product_query: str) -> List[Dict]:
        """
        Find the most liked product version matching the query.
        Aggregates reviews across all matching products and ranks by total likes and average rating.

        Args:
            product_query: Product search query (e.g., "iPhone")

        Returns:
            List of products ranked by popularity (likes + ratings)
        """
        if not self.enabled or not self.client:
            return []

        try:
            # Extract product keywords from natural language query
            product_keywords = self._extract_product_keywords(product_query)
            logger.debug(
                f"Extracted product keywords from '{product_query}': '{product_keywords}'")

            db = self.client[self.database_name]
            products_col = db[self.products_collection]
            reviews_col = db[self.reviews_collection]

            # Build search query with multiple strategies
            search_conditions = []

            # 1. Search by ObjectId if query looks like one
            if self._is_valid_objectid(product_query):
                try:
                    search_conditions.append({"_id": ObjectId(product_query)})
                except (InvalidId, ValueError):
                    pass

            # 2. Search by product name (most important!) - use extracted keywords
            search_conditions.append(
                {"name": {"$regex": product_keywords, "$options": "i"}})

            # 3. Search by brand - use extracted keywords
            search_conditions.append(
                {"brand": {"$regex": product_keywords, "$options": "i"}})

            # 4. Search by akakce_id (if numeric)
            if product_query.isdigit():
                search_conditions.append({"akakce_id": product_query})

            # 5. Search in marketplace URLs - use extracted keywords
            search_conditions.append({
                "$or": [
                    {"marketplaceOffers.hepsiburada": {
                        "$regex": product_keywords, "$options": "i"}},
                    {"marketplaceOffers.n11": {
                        "$regex": product_keywords, "$options": "i"}},
                    {"marketplaceOffers.trendyol": {
                        "$regex": product_keywords, "$options": "i"}},
                ]
            })

            search_query = {"$or": search_conditions} if len(
                search_conditions) > 1 else search_conditions[0]

            # Get more products for comparison
            products = list(products_col.find(search_query).limit(50))

            if not products:
                return []

            product_stats = []

            # Analyze each product
            for product in products:
                product_id = str(product.get(
                    "_id", product.get("productId", "")))

                # Find reviews for this product
                product_reviews = list(reviews_col.find(
                    {"productId": product_id}
                ).limit(200))

                if not product_reviews:
                    continue

                # Aggregate statistics
                ratings = []
                total_likes = 0
                review_count = 0
                marketplace_ratings = {}

                for review_doc in product_reviews:
                    # Get aggregated rating from document level
                    doc_rating = review_doc.get("rating")
                    doc_review_count = review_doc.get("reviewCount", 0)
                    marketplace = review_doc.get("marketplace", "unknown")

                    if doc_rating and doc_review_count:
                        marketplace_ratings[marketplace] = {
                            "rating": doc_rating,
                            "count": doc_review_count
                        }

                    # Process individual reviews
                    reviews_list = review_doc.get("reviews", [])
                    if isinstance(reviews_list, list):
                        for r in reviews_list:
                            rating = r.get("rating")
                            if rating:
                                ratings.append(rating)
                            total_likes += r.get("likesCount", 0)
                            review_count += 1
                    elif doc_review_count:
                        review_count += doc_review_count
                        if doc_rating:
                            # Approximate ratings from aggregated rating
                            for _ in range(min(doc_review_count, 10)):
                                ratings.append(round(doc_rating))

                if review_count == 0:
                    continue

                # Calculate average rating
                avg_rating = sum(ratings) / len(ratings) if ratings else 0
                # Use aggregated rating if available and better
                if marketplace_ratings:
                    aggregated_avg = sum(m["rating"] * m["count"] for m in marketplace_ratings.values()) / \
                        sum(m["count"] for m in marketplace_ratings.values())
                    if aggregated_avg > 0:
                        avg_rating = aggregated_avg

                # Calculate popularity score (weighted combination)
                # Formula: (avg_rating * 20) + (total_likes / 10) + (review_count / 5)
                popularity_score = (avg_rating * 20) + \
                    (total_likes / 10) + (review_count / 5)

                product_stats.append({
                    "product_id": product_id,
                    "average_rating": avg_rating,
                    "total_likes": total_likes,
                    "review_count": review_count,
                    "popularity_score": popularity_score,
                    "marketplace_offers": product.get("marketplaceOffers", {})
                })

            # Sort by popularity score
            product_stats.sort(
                key=lambda x: x["popularity_score"], reverse=True)

            # Return top results
            results = []
            for idx, stat in enumerate(product_stats[:self.max_results], 1):
                # Get product details for better context
                product_doc = next((p for p in products if str(
                    p.get("_id")) == stat['product_id']), None)
                product_name = product_doc.get(
                    "name", "Unknown Product") if product_doc else "Unknown Product"
                brand = product_doc.get("brand", "") if product_doc else ""

                result_text = f"Rank #{idx} - Most Liked Product Version\n"
                result_text += f"Product: {product_name}"
                if brand:
                    result_text += f" ({brand})"
                result_text += f"\nProduct ID: {stat['product_id']}\n"
                result_text += f"Average Rating: {stat['average_rating']:.2f}/5.0\n"
                result_text += f"Total Likes: {stat['total_likes']}\n"
                result_text += f"Review Count: {stat['review_count']}\n"
                result_text += f"Popularity Score: {stat['popularity_score']:.2f}\n"

                marketplace_offers = stat.get("marketplace_offers", {})
                if marketplace_offers:
                    hepsiburada = marketplace_offers.get("hepsiburada", [])
                    n11 = marketplace_offers.get("n11", [])
                    trendyol = marketplace_offers.get("trendyol", [])
                    total_offers = len(hepsiburada) + len(n11) + len(trendyol)
                    if total_offers > 0:
                        result_text += f"Available on: {len(hepsiburada)} Hepsiburada, {len(n11)} n11, {len(trendyol)} Trendyol offers"

                results.append({
                    "id": f"mongodb_most_liked_{stat['product_id']}",
                    # Decreasing score for lower ranks
                    "score": 0.95 - (idx * 0.05),
                    "payload": {
                        "text": result_text,
                        "source": f"mongodb://{self.database_name}/{self.reviews_collection}",
                        "chunk_id": stat['product_id'],
                        "type": "most_liked_product",
                        "product_id": stat['product_id'],
                        "rank": idx,
                        "average_rating": stat['average_rating'],
                        "total_likes": stat['total_likes'],
                        "review_count": stat['review_count'],
                        "popularity_score": stat['popularity_score']
                    }
                })

            logger.info(
                f"Found {len(results)} most liked products from MongoDB")
            return results

        except Exception as e:
            logger.error(f"MongoDB most liked product search failed: {str(e)}")
            return []

    def health_check(self) -> bool:
        """
        Check if MongoDB service is accessible.

        Returns:
            True if accessible, False otherwise
        """
        if not self.enabled:
            logger.info("MongoDB health check: Disabled (skipped)")
            return False

        if not self.client:
            logger.warning("MongoDB health check: Client not initialized")
            return False

        try:
            # Test connection
            self.client.admin.command('ping')
            logger.info("✓ MongoDB health check passed")
            return True
        except Exception as e:
            logger.error(f"✗ MongoDB health check failed: {str(e)}")
            return False
