"""
Script to embed structured chunks from JSON data.
Processes chunks and stores them in Qdrant with embeddings.
"""
import json
import logging
import hashlib
from typing import List, Dict
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from app.services.vector_db import VectorDBService
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def prepare_chunk_text(chunk: Dict) -> str:
    """
    Prepare text content from chunk for embedding.
    Combines title, type, and content for better context.

    Args:
        chunk: Chunk dictionary with content, title, type, etc.

    Returns:
        Combined text string for embedding
    """
    parts = []

    # Add title if available
    if chunk.get("title"):
        parts.append(f"Title: {chunk['title']}")

    # Add type if available
    if chunk.get("type"):
        parts.append(f"Type: {chunk['type']}")

    # Add endpoint if available
    if chunk.get("endpoint"):
        parts.append(f"Endpoint: {chunk['endpoint']}")

    # Add function/class/method if available
    if chunk.get("function"):
        parts.append(f"Function: {chunk['function']}")
    if chunk.get("class"):
        parts.append(f"Class: {chunk['class']}")
    if chunk.get("method"):
        parts.append(f"Method: {chunk['method']}")
    if chunk.get("schema"):
        parts.append(f"Schema: {chunk['schema']}")
    if chunk.get("concept"):
        parts.append(f"Concept: {chunk['concept']}")

    # Add main content
    if chunk.get("content"):
        parts.append(chunk["content"])

    # Add tags if available
    if chunk.get("tags"):
        tags_str = ", ".join(chunk["tags"])
        parts.append(f"Tags: {tags_str}")

    return "\n\n".join(parts)


def embed_chunks(chunks_data: List[Dict], source_prefix: str = "product_scraper_api") -> int:
    """
    Embed chunks and store them in Qdrant.

    Args:
        chunks_data: List of chunk dictionaries
        source_prefix: Prefix for source identifier

    Returns:
        Number of chunks successfully embedded
    """
    # Initialize Qdrant client
    qdrant_client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=30.0
    )

    # Initialize vector DB service for embedding generation
    vector_db_service = VectorDBService()

    points = []
    total_chunks = len(chunks_data)

    logger.info(f"Processing {total_chunks} chunks for embedding...")

    for idx, chunk in enumerate(chunks_data):
        try:
            # Prepare text content
            text_content = prepare_chunk_text(chunk)

            if not text_content.strip():
                logger.warning(
                    f"Skipping chunk {chunk.get('chunk_id', idx)}: empty content")
                continue

            # Generate embedding
            logger.info(
                f"Generating embedding for chunk {idx + 1}/{total_chunks}: {chunk.get('title', chunk.get('chunk_id', 'unknown'))}")
            embedding = vector_db_service.generate_embedding(text_content)

            # Create unique ID from chunk_id or generate one
            chunk_id = chunk.get("chunk_id", f"chunk_{idx:03d}")
            point_id = int(hashlib.md5(chunk_id.encode()).hexdigest()[:8], 16)

            # Prepare source identifier
            file_path = chunk.get("file_path", "unknown")
            source = f"{source_prefix}/{file_path}"

            # Prepare payload with all chunk metadata
            payload = {
                "text": text_content,
                "source": source,
                "chunk_id": chunk_id,
                "file_path": file_path,
                "chunk_index": idx,
                "total_chunks": total_chunks,
                "type": chunk.get("type", "unknown"),
                "title": chunk.get("title", ""),
            }

            # Add optional fields
            if chunk.get("endpoint"):
                payload["endpoint"] = chunk["endpoint"]
            if chunk.get("function"):
                payload["function"] = chunk["function"]
            if chunk.get("class"):
                payload["class"] = chunk["class"]
            if chunk.get("method"):
                payload["method"] = chunk["method"]
            if chunk.get("schema"):
                payload["schema"] = chunk["schema"]
            if chunk.get("concept"):
                payload["concept"] = chunk["concept"]
            if chunk.get("tags"):
                payload["tags"] = chunk["tags"]

            # Create point
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            )
            points.append(point)

            logger.debug(f"✓ Prepared chunk {chunk_id}")

        except Exception as e:
            logger.error(
                f"Error processing chunk {chunk.get('chunk_id', idx)}: {str(e)}")
            continue

    if not points:
        logger.error("No points prepared for embedding")
        return 0

    # Upsert points to Qdrant
    try:
        logger.info(
            f"Storing {len(points)} chunks in Qdrant collection '{settings.qdrant_collection_name}'")
        qdrant_client.upsert(
            collection_name=settings.qdrant_collection_name,
            points=points
        )
        logger.info(f"✓ Successfully embedded {len(points)} chunks")
        return len(points)

    except Exception as e:
        logger.error(f"Error storing chunks in Qdrant: {str(e)}")
        raise


def main():
    """Main function to embed chunks from JSON."""
    # Your chunks data
    chunks_data = [
        {
            "chunk_id": "chunk_001",
            "type": "project_overview",
            "title": "Project Overview",
            "file_path": "README.md",
            "content": "Product Scraper API is a FastAPI application for scraping product reviews from Hepsiburada and n11.com Turkish e-commerce websites. Version 1.0.0. Main technologies: FastAPI web framework, Playwright browser automation, MongoDB database, Cloudinary image hosting, httpx HTTP client, BeautifulSoup HTML parsing.",
            "tags": ["overview", "introduction", "technologies"]
        },
        {
            "chunk_id": "chunk_002",
            "type": "setup_instructions",
            "title": "Project Setup",
            "file_path": "README.md",
            "content": "Setup steps: 1) Create virtual environment with python -m venv venv, 2) Activate with source venv/bin/activate (macOS/Linux) or venv\\Scripts\\activate (Windows), 3) Install dependencies with pip install -r requirements.txt, 4) Install Playwright browsers with playwright install chromium, 5) Set environment variables: MONGODB_URI, CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, 6) Run with uvicorn main:app --reload.",
            "tags": ["setup", "installation", "configuration"]
        },
        {
            "chunk_id": "chunk_003",
            "type": "api_endpoint",
            "title": "Hepsiburada Scrape Endpoint",
            "file_path": "api/routes/scraper.py",
            "endpoint": "GET /hb/scrape",
            "content": "GET /hb/scrape endpoint scrapes product reviews from Hepsiburada. Required: Either sku or url parameter. Optional parameters: fetch_all (boolean, default false) fetches all reviews with pagination, max_pages (integer) maximum pages when fetch_all=true, page (integer, default 0) page number when fetch_all=false, size (integer, default 10, max 1000) reviews per page, delay (float, default 1.0) seconds between requests. Requires x-api-key header. Returns JSON with reviews array and metadata.",
            "tags": ["api", "endpoint", "hepsiburada", "scraping"]
        },
        {
            "chunk_id": "chunk_004",
            "type": "api_endpoint",
            "title": "n11 Scrape Endpoint",
            "file_path": "api/routes/scraper.py",
            "endpoint": "GET /n11/scrape",
            "content": "GET /n11/scrape endpoint scrapes product reviews from n11.com. Required: Either product_id or url parameter. Optional parameters: fetch_all (boolean, default false) fetches all reviews with pagination, max_pages (integer) maximum pages when fetch_all=true, page (integer, default 1, 1-indexed) page number when fetch_all=false, tag (string, default 'tümü') review filter tag, delay (float, default 1.0) seconds between requests. Requires x-api-key header. Returns JSON with reviews array and metadata.",
            "tags": ["api", "endpoint", "n11", "scraping"]
        },
        {
            "chunk_id": "chunk_005",
            "type": "api_endpoint",
            "title": "Marketplace Process Endpoint",
            "file_path": "api/routes/marketplace.py",
            "endpoint": "POST /marketplace/process",
            "content": "POST /marketplace/process endpoint processes marketplace reviews for products stored in MongoDB. Optional parameters: product_id (string) specific product ID to process, limit (integer) maximum number of products to process. Reads products from ProductReview.products collection, extracts marketplaceOffers (n11 and hepsiburada URLs), fetches all reviews for each marketplace offer, maps reviews to standard schema, saves to ProductReview.marketplace_reviews collection. Returns summary with productsProcessed, totalReviewsFetched, errors.",
            "tags": ["api", "endpoint", "marketplace", "batch_processing"]
        },
        {
            "chunk_id": "chunk_006",
            "type": "api_endpoint",
            "title": "Image Processing Endpoint",
            "file_path": "api/routes/image_processing.py",
            "endpoint": "POST /images/process-reviews",
            "content": "POST /images/process-reviews endpoint processes review images by uploading source URLs directly to Cloudinary. Optional parameters: product_id (string) specific product ID, marketplace (string) hepsiburada or n11, limit (integer) maximum products, batch_size (integer, default 10) concurrent reviews per batch. Finds reviews with sourceMediaUrls, uploads directly to Cloudinary without downloading locally, updates mediaUrls with Cloudinary URLs. Processes reviews concurrently in batches for efficiency.",
            "tags": ["api", "endpoint", "image_processing", "cloudinary"]
        },
        {
            "chunk_id": "chunk_007",
            "type": "api_endpoint",
            "title": "Image Processing Stats Endpoint",
            "file_path": "api/routes/image_processing.py",
            "endpoint": "GET /images/processing-stats",
            "content": "GET /images/processing-stats endpoint returns statistics about image processing status. Queries marketplace_reviews collection, counts total reviews with media, processed reviews with mediaUrls, unprocessed reviews with sourceMediaUrls but no mediaUrls, calculates processing percentage completion. Returns JSON with counts and percentage.",
            "tags": ["api", "endpoint", "statistics", "image_processing"]
        },
        {
            "chunk_id": "chunk_008",
            "type": "function",
            "title": "map_hepsiburada_review Function",
            "file_path": "api/routes/marketplace.py",
            "function": "map_hepsiburada_review",
            "content": "map_hepsiburada_review function maps Hepsiburada review to standard schema and uploads media to Cloudinary. Parameters: review (dict) raw review data, seller_name (string, optional), upload_media (boolean, default True), max_photos (integer, default 3). Extracts source media URLs from review.media field handling list, dict, or string formats. Uploads media to Cloudinary if enabled. Extracts review content from review.review.content nested structure. Extracts author from review.customer.displayName or name+surname. Extracts rating from review.star. Returns mapped review with id, author, rating, content, createdAt, likesCount, sellerName, isPurchaseVerified, sourceMediaUrls, mediaUrls.",
            "tags": ["function", "data_mapping", "hepsiburada", "review"]
        },
        {
            "chunk_id": "chunk_009",
            "type": "function",
            "title": "map_n11_review Function",
            "file_path": "api/routes/marketplace.py",
            "function": "map_n11_review",
            "content": "map_n11_review function maps n11 review to standard schema and uploads media to Cloudinary. Parameters: review (dict) raw review data, seller_name (string, optional), upload_media (boolean, default True), max_photos (integer, default 3). Extracts source media URLs from review.images array. Parses date from n11 format (DD/MM/YYYY) to ISO format. Uploads media to Cloudinary if enabled. Returns mapped review with id, author, rating, content, createdAt, likesCount, sellerName, sourceMediaUrls, mediaUrls. Sets isPurchaseVerified to False as n11 doesn't provide this info.",
            "tags": ["function", "data_mapping", "n11", "review"]
        },
        {
            "chunk_id": "chunk_010",
            "type": "class",
            "title": "HepsiBuradaClient Class",
            "file_path": "scrapper/hepsiburada.py",
            "class": "HepsiBuradaClient",
            "content": "HepsiBuradaClient class scrapes product reviews from Hepsiburada. Base URL: https://www.hepsiburada.com. Uses httpx for HTTP requests to Hepsiburada API. Methods: get_reviews() fetches single page, get_all_reviews() fetches all pages with pagination, _get_cookies() gets session cookies. API endpoint: https://user-content-gw-hermes.hepsiburada.com/queryapi/v2/ApprovedUserContents. Parameters: sku, includeSiblingVariantContents=true, includeSummary=true, from (page offset), size (reviews per page). Uses cookies and headers to match browser requests.",
            "tags": ["class", "scraper", "hepsiburada", "httpx"]
        },
        {
            "chunk_id": "chunk_011",
            "type": "method",
            "title": "HepsiBuradaClient.get_reviews Method",
            "file_path": "scrapper/hepsiburada.py",
            "class": "HepsiBuradaClient",
            "method": "get_reviews",
            "content": "get_reviews method fetches single page of reviews for given SKU. Parameters: sku (string, required) product SKU identifier, url (string, optional) URL for cookie generation, page (int, default 0) page offset, size (int, default 10) reviews per page. Validates SKU not empty. Gets cookies using _get_cookies method. Makes GET request to Hepsiburada API with cookies and headers. Parses JSON response, extracts reviews from data.approvedUserContent.approvedUserContentList. Returns formatted review data with reviews array and metadata including review count.",
            "tags": ["method", "hepsiburada", "scraping", "pagination"]
        },
        {
            "chunk_id": "chunk_012",
            "type": "method",
            "title": "HepsiBuradaClient.get_all_reviews Method",
            "file_path": "scrapper/hepsiburada.py",
            "class": "HepsiBuradaClient",
            "method": "get_all_reviews",
            "content": "get_all_reviews method fetches all reviews with pagination. Parameters: sku (string, required), url (string, optional), size (int, default 10), max_pages (int, optional, None for all pages), delay_between_requests (float, default 1.0). Loops through pages calling get_reviews until no more reviews found or max_pages reached. Adds delay between requests to avoid rate limiting. Combines all reviews from all pages into single response. Returns complete review data with all reviews and total count.",
            "tags": ["method", "hepsiburada", "pagination", "scraping"]
        },
        {
            "chunk_id": "chunk_013",
            "type": "class",
            "title": "N11Client Class",
            "file_path": "scrapper/n11.py",
            "class": "N11Client",
            "content": "N11Client class scrapes product reviews from n11.com. Base URL: https://www.n11.com. Uses Playwright for browser automation because n11 loads reviews with JavaScript. Browser arguments: --no-sandbox, --disable-setuid-sandbox, --disable-blink-features=AutomationControlled, --disable-dev-shm-usage. Methods: get_reviews() fetches single page, get_all_reviews() fetches all pages, _setup_browser() configures browser, _wait_for_cloudflare() bypasses Cloudflare, _load_reviews_page() navigates to reviews page.",
            "tags": ["class", "scraper", "n11", "playwright"]
        },
        {
            "chunk_id": "chunk_014",
            "type": "method",
            "title": "N11Client._wait_for_cloudflare Method",
            "file_path": "scrapper/n11.py",
            "class": "N11Client",
            "method": "_wait_for_cloudflare",
            "content": "_wait_for_cloudflare method waits for Cloudflare challenge to complete. Parameters: page_instance (Playwright page), max_wait (int, default 90) maximum wait seconds. Checks page title for 'cloudflare' or 'attention required'. Waits up to 90 seconds, scrolls page periodically to simulate human behavior. Returns True when Cloudflare challenge passes. Raises exception if challenge not bypassed after 90 seconds.",
            "tags": ["method", "n11", "cloudflare", "bypass"]
        },
        {
            "chunk_id": "chunk_015",
            "type": "function",
            "title": "get_api_key_with_rate_limit Function",
            "file_path": "api/middleware/auth.py",
            "function": "get_api_key_with_rate_limit",
            "content": "get_api_key_with_rate_limit function validates API key and enforces rate limiting. Parameter: x_api_key (string) from x-api-key header. Validates API key against VALID_API_KEYS set. Rate limiting: 10 requests per 60 seconds per API key using in-memory storage. Removes requests outside time window, checks if rate limit exceeded, records current request timestamp. Raises HTTPException 401 if invalid API key, 429 if rate limit exceeded. Returns validated API key string.",
            "tags": ["function", "authentication", "rate_limiting", "middleware"]
        },
        {
            "chunk_id": "chunk_016",
            "type": "function",
            "title": "extract_sku_from_url Function",
            "file_path": "scrapper/utils.py",
            "function": "extract_sku_from_url",
            "content": "extract_sku_from_url function extracts SKU from Hepsiburada product URL. Parameter: url (string) Hepsiburada product URL. Removes query string and fragment. Patterns: -p-([A-Z]{3,4}\\d+[A-Z0-9]+), -pm-([A-Z]{3,4}\\d+[A-Z0-9]+), -([A-Z]{3,4}\\d+[A-Z0-9]+)-, /([A-Z]{3,4}\\d+[A-Z0-9]+). Validates SKU starts with HBC and length at least 10. Returns SKU uppercase or None. Examples: https://www.hepsiburada.com/product-pm-HBC00006IUW8W-yorumlari extracts HBC00006IUW8W.",
            "tags": ["function", "utility", "url_parsing", "hepsiburada"]
        },
        {
            "chunk_id": "chunk_017",
            "type": "function",
            "title": "extract_product_id_from_n11_url Function",
            "file_path": "scrapper/utils.py",
            "function": "extract_product_id_from_n11_url",
            "content": "extract_product_id_from_n11_url function extracts product ID from n11.com product URL. Parameter: url (string) n11.com product URL. Removes query string and fragment. Patterns: -(\\d+)$ matches numbers at end, /urun/[^/]+-(\\d+)$ matches /urun/product-name-ID, productId=(\\d+) matches query param. Validates product ID is numeric and length at least 6. Returns product ID string or None. Examples: https://www.n11.com/urun/product-name-46377738 extracts 46377738.",
            "tags": ["function", "utility", "url_parsing", "n11"]
        },
        {
            "chunk_id": "chunk_018",
            "type": "function",
            "title": "configure_cloudinary Function",
            "file_path": "utils/cloudinary_upload.py",
            "function": "configure_cloudinary",
            "content": "configure_cloudinary function configures Cloudinary with environment variables. Supports CLOUDINARY_URL format: cloudinary://api_key:api_secret@cloud_name or individual variables: CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, CLOUDINARY_CLOUD_NAME. Tries CLOUDINARY_URL first, falls back to individual variables, tries manual parsing if needed. Sets global _cloudinary_configured flag. Logs configuration status. Raises warning if configuration fails.",
            "tags": ["function", "cloudinary", "configuration"]
        },
        {
            "chunk_id": "chunk_019",
            "type": "function",
            "title": "upload_media_url Function",
            "file_path": "utils/cloudinary_upload.py",
            "function": "upload_media_url",
            "content": "upload_media_url function uploads media URL directly to Cloudinary (most efficient method). Cloudinary downloads image directly from source URL eliminating need to download to server. Parameters: source_url (string) source URL of image, folder (string, default 'review-media') Cloudinary folder path, public_id (string, optional) public ID for image. Replaces {size}, {width}, {height} placeholders with 800. Uses uploader.upload with folder, public_id, resource_type='image', overwrite=false, invalidate=true. Returns secure_url or url from result, None if upload fails.",
            "tags": ["function", "cloudinary", "image_upload"]
        },
        {
            "chunk_id": "chunk_020",
            "type": "function",
            "title": "process_media_urls Function",
            "file_path": "utils/cloudinary_upload.py",
            "function": "process_media_urls",
            "content": "process_media_urls function processes list of media URLs uploading directly to Cloudinary. Parameters: source_media_urls (list of dicts) with 'id' and 'url' keys, folder (string, default 'review-media') Cloudinary folder path, review_id (string, optional) review ID to associate with media. Generates public_id from review_id and media_id if available. Uploads each media item using upload_media_url. Returns list of dicts with 'url' (Cloudinary URL) and 'sourceUrl' (original URL). Handles both string array and object array formats for sourceMediaUrls.",
            "tags": ["function", "cloudinary", "batch_upload"]
        },
        {
            "chunk_id": "chunk_021",
            "type": "class",
            "title": "ImageProcessingService Class",
            "file_path": "services/image_processing.py",
            "class": "ImageProcessingService",
            "content": "ImageProcessingService class processes review images and uploads to Cloudinary using direct URL uploads. Initializes with Cloudinary configuration calling configure_cloudinary. Gets marketplace_reviews collection from MongoDB. Methods: process_review_media() processes single review, process_product_reviews() processes product reviews, process_all_products() processes all products, get_processing_stats() gets statistics. Processes reviews concurrently in batches for efficiency.",
            "tags": ["class", "service", "image_processing", "cloudinary"]
        },
        {
            "chunk_id": "chunk_022",
            "type": "method",
            "title": "ImageProcessingService.process_review_media Method",
            "file_path": "services/image_processing.py",
            "class": "ImageProcessingService",
            "method": "process_review_media",
            "content": "process_review_media method processes media for single review. Parameters: review (dict) review document, marketplace (string) 'hepsiburada' or 'n11'. Extracts review_id and sourceMediaUrls. Handles both string array format ['url1', 'url2'] and object array format [{'id': 1, 'url': 'url1'}]. Converts to format expected by process_media_urls with id and url keys. Determines folder based on marketplace: 'review-media/hepsiburada' or 'review-media/n11'. Calls process_media_urls to upload media. Converts processed media to expected format for mediaUrls with id, reviewId, url fields. Returns updated review dict.",
            "tags": ["method", "image_processing", "review"]
        },
        {
            "chunk_id": "chunk_023",
            "type": "function",
            "title": "get_mongodb_client Function",
            "file_path": "database/mongodb.py",
            "function": "get_mongodb_client",
            "content": "get_mongodb_client function gets or creates MongoDB client singleton. Reads MONGODB_URI from environment variable. Creates MongoClient with connection string. Returns client instance. Raises ValueError if MONGODB_URI not set. Uses global _client variable for singleton pattern to reuse connections across requests.",
            "tags": ["function", "database", "mongodb", "connection"]
        },
        {
            "chunk_id": "chunk_024",
            "type": "function",
            "title": "get_products_collection Function",
            "file_path": "database/mongodb.py",
            "function": "get_products_collection",
            "content": "get_products_collection function gets products collection from ProductReview database. Calls get_database() to get database instance. Returns db.products collection. Used to query and update product documents stored in MongoDB.",
            "tags": ["function", "database", "mongodb", "collection"]
        },
        {
            "chunk_id": "chunk_025",
            "type": "function",
            "title": "get_marketplace_reviews_collection Function",
            "file_path": "database/mongodb.py",
            "function": "get_marketplace_reviews_collection",
            "content": "get_marketplace_reviews_collection function gets marketplace_reviews collection from ProductReview database. Calls get_database() to get database instance. Returns db.marketplace_reviews collection. Used to query and update marketplace review documents stored in MongoDB. Each document contains productId, marketplace, offerUrl, and reviews array.",
            "tags": ["function", "database", "mongodb", "collection"]
        },
        {
            "chunk_id": "chunk_026",
            "type": "data_model",
            "title": "Review Schema",
            "file_path": "api/routes/marketplace.py",
            "schema": "review",
            "content": "Review schema standard format: id (string) review ID, author (string) reviewer name, rating (integer) 1-5 star rating, content (string) review text content, createdAt (string) ISO 8601 date with Z suffix, likesCount (integer) helpful count, sellerName (string) merchant seller name, isPurchaseVerified (boolean) purchase verification flag, sourceMediaUrls (array) original media URLs as strings or objects, mediaUrls (array) Cloudinary URLs with id, reviewId, url fields. Used by both Hepsiburada and n11 reviews after mapping.",
            "tags": ["schema", "data_model", "review"]
        },
        {
            "chunk_id": "chunk_027",
            "type": "data_model",
            "title": "Product Schema",
            "file_path": "database/mongodb.py",
            "schema": "product",
            "content": "Product schema format: productId (string) MongoDB ObjectId, marketplaceOffers (object) containing hepsiburada (array of URLs) and n11 (array of URLs). Stored in ProductReview.products collection. Used by /marketplace/process endpoint to fetch reviews for each marketplace offer.",
            "tags": ["schema", "data_model", "product"]
        },
        {
            "chunk_id": "chunk_028",
            "type": "data_model",
            "title": "Marketplace Review Document Schema",
            "file_path": "database/mongodb.py",
            "schema": "marketplace_review",
            "content": "Marketplace review document schema: productId (string) product ID, marketplace (string) 'hepsiburada' or 'n11', offerUrl (string) marketplace offer URL, reviews (array) array of review objects in standard schema format. Stored in ProductReview.marketplace_reviews collection. Each document represents reviews for one product from one marketplace offer.",
            "tags": ["schema", "data_model", "marketplace_review"]
        },
        {
            "chunk_id": "chunk_029",
            "type": "concept",
            "title": "Concurrent Processing",
            "file_path": "api/routes/marketplace.py",
            "concept": "concurrent_processing",
            "content": "Concurrent processing allows processing multiple products or reviews simultaneously using asyncio.gather for faster performance. Instead of processing one product at a time sequentially, multiple products are processed in parallel. Example: Processing 5 products concurrently vs one after another. Used in /marketplace/process endpoint and image processing endpoints. Improves performance significantly especially when processing large batches.",
            "tags": ["concept", "performance", "async", "concurrency"]
        },
        {
            "chunk_id": "chunk_030",
            "type": "concept",
            "title": "Rate Limiting",
            "file_path": "api/middleware/auth.py",
            "concept": "rate_limiting",
            "content": "Rate limiting limits API requests to 10 per minute per API key using in-memory storage. Prevents abuse and protects the system. Uses _rate_limit_store dictionary mapping API keys to request timestamps. Removes requests outside 60-second time window. Raises HTTPException 429 if rate limit exceeded. In production should use Redis or similar for distributed rate limiting instead of in-memory storage.",
            "tags": ["concept", "security", "rate_limiting"]
        },
        {
            "chunk_id": "chunk_031",
            "type": "concept",
            "title": "Cookie Generation",
            "file_path": "scrapper/cookies.py",
            "concept": "cookie_generation",
            "content": "Cookie generation creates valid session cookies by visiting websites to access protected content. Some sites require cookies (like login tokens) to show content. Cookies are generated by navigating to product pages using Playwright or httpx. Ensures requests look like legitimate browser requests. Used by Hepsiburada scraper to get cookies before making API requests.",
            "tags": ["concept", "scraping", "cookies", "authentication"]
        },
        {
            "chunk_id": "chunk_032",
            "type": "concept",
            "title": "Cloudflare Bypass",
            "file_path": "scrapper/n11.py",
            "concept": "cloudflare_bypass",
            "content": "Cloudflare bypass waits for Cloudflare challenge to complete by checking page title and simulating human behavior. Cloudflare protects sites from bots. _wait_for_cloudflare method checks page title for 'cloudflare' or 'attention required'. Waits up to 90 seconds, scrolls page periodically to simulate human behavior. Returns True when Cloudflare challenge passes. Raises exception if challenge not bypassed after 90 seconds.",
            "tags": ["concept", "scraping", "cloudflare", "bypass"]
        },
        {
            "chunk_id": "chunk_033",
            "type": "concept",
            "title": "Direct URL Upload",
            "file_path": "utils/cloudinary_upload.py",
            "concept": "direct_url_upload",
            "content": "Direct URL upload is Cloudinary feature to upload images directly from source URLs without downloading to server first. More efficient: no memory usage on server, no bandwidth usage on server, faster parallel processing on Cloudinary infrastructure, more reliable Cloudinary handles retries and timeouts. Used by upload_media_url function. Cloudinary downloads image from source URL on their end.",
            "tags": ["concept", "cloudinary", "image_upload", "performance"]
        },
        {
            "chunk_id": "chunk_034",
            "type": "concept",
            "title": "Data Mapping",
            "file_path": "api/routes/marketplace.py",
            "concept": "data_mapping",
            "content": "Data mapping converts review data from different marketplace formats (Hepsiburada, n11) to standardized schema. Hepsiburada uses nested structure: review.review.content, review.customer.displayName, review.star, review.reactions.clap. n11 uses flat structure: review.comment, review.author, review.rating, review.images. Both mapped to standard schema with id, author, rating, content, createdAt, likesCount, sellerName, isPurchaseVerified, sourceMediaUrls, mediaUrls fields.",
            "tags": ["concept", "data_transformation", "mapping"]
        },
        {
            "chunk_id": "chunk_035",
            "type": "concept",
            "title": "Pagination",
            "file_path": "scrapper/hepsiburada.py",
            "concept": "pagination",
            "content": "Pagination fetches reviews page by page with configurable delays and maximum page limits. Used by get_all_reviews methods in both HepsiburadaClient and N11Client. Parameters: page offset or number, size reviews per page, max_pages maximum pages to fetch (None for all), delay_between_requests seconds between requests. Loops through pages until no more reviews found or max_pages reached. Combines all reviews from all pages into single response.",
            "tags": ["concept", "pagination", "scraping"]
        },
        {
            "chunk_id": "chunk_036",
            "type": "configuration",
            "title": "Environment Variables",
            "file_path": ".env",
            "content": "Required environment variables: MONGODB_URI MongoDB connection string format mongodb+srv://user:password@cluster.mongodb.net/, CLOUDINARY_CLOUD_NAME Cloudinary cloud name, CLOUDINARY_API_KEY Cloudinary API key, CLOUDINARY_API_SECRET Cloudinary API secret. Optional: CLOUDINARY_URL format cloudinary://api_key:api_secret@cloud_name. Can use CLOUDINARY_URL or individual variables. Set in .env file or system environment variables.",
            "tags": ["configuration", "environment_variables"]
        },
        {
            "chunk_id": "chunk_037",
            "type": "configuration",
            "title": "API Keys Configuration",
            "file_path": "api/middleware/auth.py",
            "content": "API keys are configured in VALID_API_KEYS set in api/middleware/auth.py. Default keys: 'test-api-key-123', 'dev-api-key-456'. In production should store in environment variables or database instead of hardcoded set. All API endpoints require x-api-key header with valid key. Invalid keys return 401 Unauthorized error.",
            "tags": ["configuration", "api_keys", "security"]
        },
        {
            "chunk_id": "chunk_038",
            "type": "configuration",
            "title": "Rate Limit Configuration",
            "file_path": "api/middleware/auth.py",
            "content": "Rate limit configuration: RATE_LIMIT_REQUESTS = 10 requests per window, RATE_LIMIT_WINDOW = 60 seconds. Can be adjusted in api/middleware/auth.py. Applies per API key. Exceeding rate limit returns 429 Too Many Requests error. Uses in-memory storage, should use Redis in production for distributed systems.",
            "tags": ["configuration", "rate_limiting"]
        },
        {
            "chunk_id": "chunk_039",
            "type": "main_entry",
            "title": "FastAPI Application Initialization",
            "file_path": "main.py",
            "content": "main.py is FastAPI application entry point. Loads environment variables from .env file using dotenv. Ensures Playwright browsers are installed checking PLAYWRIGHT_BROWSERS_PATH and common cache locations. Configures Cloudinary on startup. Creates FastAPI app with title 'Product Scraper API', description, version '1.0.0'. Includes routers: scraper at /hb, n11_router at /n11, marketplace at /marketplace, image_processing at /images. Root endpoint returns message and version. Health check endpoint returns status healthy.",
            "tags": ["main", "initialization", "fastapi"]
        },
        {
            "chunk_id": "chunk_040",
            "type": "deployment",
            "title": "Vercel Deployment",
            "file_path": "vercel.json",
            "content": "Vercel deployment configuration in vercel.json. buildCommand: pip install -r requirements.txt && python -m playwright install chromium. installCommand: pip install -r requirements.txt. devCommand: uvicorn main:app --reload --host 0.0.0.0 --port $PORT. rewrites all requests to /api/index for serverless functions. api/index.py creates Mangum handler for Vercel serverless functions with lifespan='off'.",
            "tags": ["deployment", "vercel", "serverless"]
        }
    ]

    # Embed all chunks
    try:
        count = embed_chunks(chunks_data, source_prefix="product_scraper_api")
        logger.info(f"✓ Successfully embedded {count} chunks")
        return count
    except Exception as e:
        logger.error(f"Failed to embed chunks: {str(e)}")
        raise


if __name__ == "__main__":
    main()
