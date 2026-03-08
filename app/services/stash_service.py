"""
Stash/Bitbucket service for searching code repositories.
Supports searching code, files, and repositories using Stash/Bitbucket REST API.
"""
import logging
import requests
from typing import List, Dict, Optional
from urllib.parse import quote
from app.core.config import settings

logger = logging.getLogger(__name__)


class StashService:
    """Service for searching code repositories via Stash/Bitbucket API."""

    def __init__(self):
        """Initialize Stash service with configuration."""
        logger.info(f"Initializing StashService")
        logger.info(f"Base URL: {settings.stash_base_url}")
        logger.info(f"Enabled: {settings.stash_enabled}")

        self.base_url = settings.stash_base_url.rstrip("/")
        self.username = settings.stash_username
        self.password = settings.stash_password
        self.token = settings.stash_token
        self.enabled = settings.stash_enabled
        self.max_results = settings.stash_max_results
        self.timeout = settings.stash_timeout

        # Determine authentication method
        if self.token:
            self.auth = None
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            logger.info("✓ Using Bearer token authentication")
        elif self.username and self.password:
            self.auth = (self.username, self.password)
            self.headers = {"Content-Type": "application/json"}
            logger.info(
                f"✓ Using username/password authentication (user: {self.username})")
        else:
            self.auth = None
            self.headers = {"Content-Type": "application/json"}
            if self.enabled:
                logger.warning("✗ No authentication configured for Stash")

        if self.enabled:
            logger.info(f"✓ StashService initialized (enabled)")
        else:
            logger.info(f"✓ StashService initialized (disabled)")

    def search_code(self, query: str, repositories: Optional[List[str]] = None) -> List[Dict]:
        """
        Search for code across repositories.

        Args:
            query: Search query string
            repositories: Optional list of repository slugs to search in

        Returns:
            List of search results with code snippets and metadata
        """
        if not self.enabled:
            return []

        try:
            results = []

            # Stash/Bitbucket code search endpoint
            # Note: Bitbucket Server uses different endpoints than Bitbucket Cloud
            if settings.stash_is_bitbucket_cloud:
                # Bitbucket Cloud API
                search_url = f"{self.base_url}/2.0/repositories/{settings.stash_workspace}/search/code"
                params = {
                    "search_query": query,
                    "page": 1,
                    "pagelen": self.max_results
                }
            else:
                # Bitbucket Server/Stash API
                search_url = f"{self.base_url}/rest/api/1.0/search"
                params = {
                    "q": query,
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

            # Parse results based on API version
            if settings.stash_is_bitbucket_cloud:
                items = data.get("values", [])
                for item in items:
                    file_path = item.get("file", {}).get("path", "")
                    repo_name = item.get("repository", {}).get("name", "")
                    content_match = item.get("content_match", "")

                    results.append({
                        "id": f"stash_{item.get('file', {}).get('hash', '')}",
                        "score": 0.8,  # Default score for code search
                        "payload": {
                            "text": content_match or f"Code in {file_path}",
                            "source": f"stash://{repo_name}/{file_path}",
                            "chunk_id": item.get("file", {}).get("hash", ""),
                            "type": "code",
                            "repository": repo_name,
                            "file_path": file_path,
                            "line_number": item.get("line", None)
                        }
                    })
            else:
                # Bitbucket Server format
                code_results = data.get(
                    "codeSearchResults", {}).get("values", [])
                for item in code_results:
                    results.append({
                        "id": f"stash_{item.get('id', '')}",
                        "score": 0.8,
                        "payload": {
                            "text": item.get("matchedContent", ""),
                            "source": f"stash://{item.get('repository', {}).get('name', '')}/{item.get('file', {}).get('path', '')}",
                            "chunk_id": item.get("id", ""),
                            "type": "code",
                            "repository": item.get("repository", {}).get("name", ""),
                            "file_path": item.get("file", {}).get("path", ""),
                            "line_number": item.get("line", None)
                        }
                    })

            logger.info(f"Found {len(results)} code results from Stash")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Stash code search failed: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in Stash search: {str(e)}")
            return []

    def search_repositories(self, query: str) -> List[Dict]:
        """
        Search for repositories by name or description.

        Args:
            query: Search query string

        Returns:
            List of repository results
        """
        if not self.enabled:
            return []

        try:
            results = []

            if settings.stash_is_bitbucket_cloud:
                search_url = f"{self.base_url}/2.0/repositories/{settings.stash_workspace}"
                params = {
                    "q": f"name ~ \"{query}\"",
                    "pagelen": self.max_results
                }
            else:
                search_url = f"{self.base_url}/rest/api/1.0/repos"
                params = {
                    "name": query,
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
            repos = data.get(
                "values", []) if settings.stash_is_bitbucket_cloud else data.get("values", [])

            for repo in repos:
                repo_name = repo.get("name", "")
                repo_desc = repo.get("description", "") or repo.get(
                    "description", "")

                results.append({
                    "id": f"stash_repo_{repo.get('uuid', repo.get('id', ''))}",
                    "score": 0.7,
                    "payload": {
                        "text": f"Repository: {repo_name}\n{repo_desc}",
                        "source": f"stash://{repo_name}",
                        "chunk_id": repo.get("uuid", repo.get("id", "")),
                        "type": "repository",
                        "repository": repo_name
                    }
                })

            logger.info(f"Found {len(results)} repository results from Stash")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Stash repository search failed: {str(e)}")
            return []
        except Exception as e:
            logger.error(
                f"Unexpected error in Stash repository search: {str(e)}")
            return []

    def health_check(self) -> bool:
        """
        Check if Stash service is accessible.

        Returns:
            True if accessible, False otherwise
        """
        if not self.enabled:
            logger.info("Stash health check: Disabled (skipped)")
            return False

        logger.info(f"Checking Stash health ({self.base_url})")
        try:
            # Try to access a simple endpoint
            if settings.stash_is_bitbucket_cloud:
                url = f"{self.base_url}/2.0/user"
                logger.debug(f"Testing Bitbucket Cloud endpoint: {url}")
            else:
                url = f"{self.base_url}/rest/api/1.0/application-properties"
                logger.debug(f"Testing Stash/Bitbucket Server endpoint: {url}")

            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                timeout=5
            )
            is_healthy = response.status_code == 200
            if is_healthy:
                logger.info("✓ Stash health check passed")
            else:
                logger.warning(
                    f"✗ Stash health check failed: HTTP {response.status_code}")
            return is_healthy
        except Exception as e:
            logger.error(f"✗ Stash health check failed: {str(e)}")
            return False
