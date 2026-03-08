"""
Confluence service for searching documentation.
Supports searching pages, spaces, and content using Confluence REST API.
Supports both /rest/api/content/search and /wiki/rest/api/search endpoints.
"""
import logging
import re
import requests
from typing import List, Dict, Optional
from urllib.parse import quote
from requests.auth import HTTPBasicAuth
from app.core.config import settings

logger = logging.getLogger(__name__)


class ConfluenceService:
    """Service for searching Confluence documentation."""

    def __init__(self):
        """Initialize Confluence service with configuration."""
        logger.info(f"Initializing ConfluenceService")
        logger.info(f"Base URL: {settings.confluence_base_url}")
        logger.info(f"Enabled: {settings.confluence_enabled}")
        logger.info(f"Wiki Search: {settings.confluence_use_wiki_search}")

        self.base_url = settings.confluence_base_url.rstrip("/")
        self.username = settings.confluence_username
        self.password = settings.confluence_password
        self.token = settings.confluence_token
        self.enabled = settings.confluence_enabled
        self.use_wiki_search = settings.confluence_use_wiki_search
        self.max_results = settings.confluence_max_results
        self.timeout = settings.confluence_timeout
        self.space_keys = settings.confluence_space_keys.split(
            ",") if settings.confluence_space_keys else None

        # Determine authentication method
        if self.token:
            self.auth = None
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            logger.info("✓ Using Bearer token authentication")
        elif self.username and self.password:
            # For wiki search endpoint, use HTTPBasicAuth
            if self.use_wiki_search:
                self.auth = HTTPBasicAuth(self.username, self.password)
                logger.info(f"✓ Using HTTPBasicAuth (user: {self.username})")
            else:
                self.auth = (self.username, self.password)
                logger.info(
                    f"✓ Using username/password authentication (user: {self.username})")
            self.headers = {"Content-Type": "application/json"}
        else:
            self.auth = None
            self.headers = {"Content-Type": "application/json"}
            if self.enabled:
                logger.warning("✗ No authentication configured for Confluence")

        if self.enabled:
            search_endpoint = "/wiki/rest/api/search" if self.use_wiki_search else "/rest/api/content/search"
            logger.info(
                f"✓ ConfluenceService initialized (enabled, endpoint: {search_endpoint})")
        else:
            logger.info(f"✓ ConfluenceService initialized (disabled)")

    def search_content(self, query: str, space_keys: Optional[List[str]] = None) -> List[Dict]:
        """
        Search for content in Confluence.

        Args:
            query: Search query string
            space_keys: Optional list of space keys to search in

        Returns:
            List of search results with content snippets and metadata
        """
        if not self.enabled:
            return []

        # Use wiki search endpoint if enabled
        if self.use_wiki_search:
            return self._search_wiki_api(query, space_keys)
        else:
            return self._search_content_api(query, space_keys)

    def _search_wiki_api(self, query: str, space_keys: Optional[List[str]] = None) -> List[Dict]:
        """
        Search using /wiki/rest/api/search endpoint (CQL search).

        Args:
            query: Search query string
            space_keys: Optional list of space keys to search in

        Returns:
            List of search results
        """
        try:
            results = []
            spaces_to_search = space_keys or self.space_keys or []

            # Use /wiki/rest/api/search endpoint
            search_url = f"{self.base_url}/wiki/rest/api/search"

            # Build CQL query
            cql_query = f"text ~ \"{query}\""
            if spaces_to_search:
                space_filter = " OR ".join(
                    [f"space = {key}" for key in spaces_to_search])
                cql_query = f"({cql_query}) AND ({space_filter})"

            params = {
                "cql": cql_query
            }

            headers = {
                "Accept": "application/json"
            }

            response = requests.get(
                search_url,
                params=params,
                auth=self.auth,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            pages = data.get("results", [])

            for page in pages[:self.max_results]:
                page_id = page.get("id", "")
                page_title = page.get("title", "")
                space_key = page.get("space", {}).get("key", "")
                space_name = page.get("space", {}).get("name", "")

                # Extract text content from body
                body_storage = page.get("body", {}).get(
                    "storage", {}).get("value", "")
                # Remove HTML tags for cleaner text (simple approach)
                text_content = re.sub(r'<[^>]+>', '', body_storage)
                text_content = text_content[:1000]  # Limit length

                # Build source URL
                page_url = f"{self.base_url}/pages/viewpage.action?pageId={page_id}"

                results.append({
                    "id": f"confluence_{page_id}",
                    "score": 0.85,  # Default score for Confluence search
                    "payload": {
                        "text": f"{page_title}\n\n{text_content}",
                        "source": f"confluence://{space_key}/{page_title}",
                        "chunk_id": page_id,
                        "type": "documentation",
                        "space": space_key,
                        "space_name": space_name,
                        "page_id": page_id,
                        "page_url": page_url,
                        "page_title": page_title
                    }
                })

            logger.info(
                f"Found {len(results)} content results from Confluence (wiki search)")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Confluence wiki search failed: {str(e)}")
            return []
        except Exception as e:
            logger.error(
                f"Unexpected error in Confluence wiki search: {str(e)}")
            return []

    def _search_content_api(self, query: str, space_keys: Optional[List[str]] = None) -> List[Dict]:
        """
        Search using /rest/api/content/search endpoint (original method).

        Args:
            query: Search query string
            space_keys: Optional list of space keys to search in

        Returns:
            List of search results
        """
        try:
            results = []
            spaces_to_search = space_keys or self.space_keys or []

            # Confluence Content Search API (CQL - Confluence Query Language)
            search_url = f"{self.base_url}/rest/api/content/search"

            # Build CQL query
            cql_query = f"text ~ \"{query}\""
            if spaces_to_search:
                space_filter = " OR ".join(
                    [f"space = {key}" for key in spaces_to_search])
                cql_query = f"({cql_query}) AND ({space_filter})"

            params = {
                "cql": cql_query,
                "limit": self.max_results,
                "expand": "body.storage,space,version"
            }

            response = requests.get(
                search_url,
                params=params,
                auth=self.auth,
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            pages = data.get("results", [])

            for page in pages:
                page_id = page.get("id", "")
                page_title = page.get("title", "")
                space_key = page.get("space", {}).get("key", "")
                space_name = page.get("space", {}).get("name", "")

                # Extract text content from body
                body_storage = page.get("body", {}).get(
                    "storage", {}).get("value", "")
                # Remove HTML tags for cleaner text (simple approach)
                text_content = re.sub(r'<[^>]+>', '', body_storage)
                text_content = text_content[:1000]  # Limit length

                # Build source URL
                page_url = f"{self.base_url}/pages/viewpage.action?pageId={page_id}"

                results.append({
                    "id": f"confluence_{page_id}",
                    "score": 0.85,  # Default score for Confluence search
                    "payload": {
                        "text": f"{page_title}\n\n{text_content}",
                        "source": f"confluence://{space_key}/{page_title}",
                        "chunk_id": page_id,
                        "type": "documentation",
                        "space": space_key,
                        "space_name": space_name,
                        "page_id": page_id,
                        "page_url": page_url,
                        "page_title": page_title
                    }
                })

            logger.info(
                f"Found {len(results)} content results from Confluence (content search)")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Confluence content search failed: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in Confluence search: {str(e)}")
            return []

    def search_spaces(self, query: str) -> List[Dict]:
        """
        Search for spaces by name or key.

        Args:
            query: Search query string

        Returns:
            List of space results
        """
        if not self.enabled:
            return []

        try:
            results = []

            search_url = f"{self.base_url}/rest/api/space"
            params = {
                "type": "global",
                "limit": self.max_results
            }

            response = requests.get(
                search_url,
                params=params,
                auth=self.auth,
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            spaces = data.get("results", [])

            # Filter spaces by query
            filtered_spaces = [
                s for s in spaces
                if query.lower() in s.get("name", "").lower() or
                query.lower() in s.get("key", "").lower()
            ]

            for space in filtered_spaces[:self.max_results]:
                space_key = space.get("key", "")
                space_name = space.get("name", "")
                space_desc = space.get("description", {}).get(
                    "plain", {}).get("value", "")

                results.append({
                    "id": f"confluence_space_{space_key}",
                    "score": 0.7,
                    "payload": {
                        "text": f"Space: {space_name}\n{space_desc}",
                        "source": f"confluence://{space_key}",
                        "chunk_id": space_key,
                        "type": "space",
                        "space": space_key,
                        "space_name": space_name
                    }
                })

            logger.info(f"Found {len(results)} space results from Confluence")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Confluence space search failed: {str(e)}")
            return []
        except Exception as e:
            logger.error(
                f"Unexpected error in Confluence space search: {str(e)}")
            return []

    def health_check(self) -> bool:
        """
        Check if Confluence service is accessible.

        Returns:
            True if accessible, False otherwise
        """
        if not self.enabled:
            logger.info("Confluence health check: Disabled (skipped)")
            return False

        logger.info(f"Checking Confluence health ({self.base_url})")
        try:
            # Try to access a simple endpoint
            url = f"{self.base_url}/rest/api/user/current"
            logger.debug(f"Testing Confluence endpoint: {url}")
            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                timeout=5
            )
            is_healthy = response.status_code == 200
            if is_healthy:
                logger.info("✓ Confluence health check passed")
            else:
                logger.warning(
                    f"✗ Confluence health check failed: HTTP {response.status_code}")
            return is_healthy
        except Exception as e:
            logger.error(f"✗ Confluence health check failed: {str(e)}")
            return False
