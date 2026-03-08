"""
Embedding service supporting multiple providers.
Supports AWS Bedrock, local models (sentence-transformers), and OpenAI.
"""
import logging
from typing import List, Optional
import json
import requests
import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings from multiple providers."""

    def __init__(self, provider: str = "bedrock", **kwargs):
        """
        Initialize embedding service.

        Args:
            provider: Embedding provider ('bedrock', 'local', 'openai')
            **kwargs: Provider-specific configuration
        """
        self.provider = provider.lower()

        if self.provider == "bedrock":
            self._init_bedrock(**kwargs)
        elif self.provider == "local":
            self._init_local(**kwargs)
        elif self.provider == "openai":
            self._init_openai(**kwargs)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")

    def _init_bedrock(self, region: str, access_key_id: Optional[str] = None,
                      secret_access_key: Optional[str] = None, api_key: Optional[str] = None,
                      bearer_token: Optional[str] = None, aws_profile: Optional[str] = None,
                      model_id: str = "amazon.titan-embed-text-v2:0",
                      dimension: int = 1024):
        """Initialize AWS Bedrock embedding service."""
        self.region = region
        self.model_id = model_id
        self.dimension = dimension
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.aws_profile = aws_profile
        # Priority: AWS Profile > bearer token > API key > AWS credentials
        self.use_bearer_token = bearer_token is not None and not aws_profile
        self.use_api_key = api_key is not None and not self.use_bearer_token and not aws_profile

        # Validate dimension for Titan V2
        if "titan-embed-text-v2" in model_id:
            if dimension not in [1024, 512, 256]:
                raise ValueError(
                    f"Titan V2 supports dimensions 1024, 512, or 256. Got: {dimension}")
        elif "titan-embed-text-v1" in model_id:
            self.dimension = 1536  # V1 is fixed at 1536
        else:
            # Default for other models
            self.dimension = dimension if dimension else 1024

        # Use bearer token, API key, or boto3 with AWS credentials
        # Store AWS credentials for potential fallback
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key

        # Prioritize AWS Profile if specified
        if aws_profile:
            session = boto3.Session(profile_name=aws_profile)
            self.bedrock_runtime = session.client(
                service_name="bedrock-runtime",
                region_name=region
            )
            logger.info(
                f"Initialized Bedrock embedding with AWS Profile '{aws_profile}': {model_id} with dimension {self.dimension}")
        elif self.use_bearer_token:
            self.bedrock_endpoint = f"https://bedrock-runtime.{region}.amazonaws.com"
            logger.info(
                f"Initialized Bedrock embedding with Bearer token: {model_id} with dimension {self.dimension}")
            # Initialize AWS credentials as fallback if available
            if access_key_id and secret_access_key:
                self.bedrock_runtime = boto3.client(
                    service_name="bedrock-runtime",
                    region_name=region,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key
                )
                logger.info("✓ AWS credentials available for fallback")
        elif self.use_api_key:
            self.bedrock_endpoint = f"https://bedrock-runtime.{region}.amazonaws.com"
            logger.info(
                f"Initialized Bedrock embedding with API key: {model_id} with dimension {self.dimension}")
            # Initialize AWS credentials as fallback if available
            if access_key_id and secret_access_key:
                self.bedrock_runtime = boto3.client(
                    service_name="bedrock-runtime",
                    region_name=region,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key
                )
                logger.info("✓ AWS credentials available for fallback")
        else:
            if access_key_id and secret_access_key:
                self.bedrock_runtime = boto3.client(
                    service_name="bedrock-runtime",
                    region_name=region,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key
                )
                logger.info(
                    f"Initialized Bedrock embedding with AWS credentials: {model_id} with dimension {self.dimension}")
            else:
                # Use default credential chain
                self.bedrock_runtime = boto3.client(
                    service_name="bedrock-runtime",
                    region_name=region
                )
                logger.info(
                    f"Initialized Bedrock embedding with default AWS credential chain: {model_id} with dimension {self.dimension}")

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text.

        Args:
            text: Text to generate embedding for

        Returns:
            List of float values representing the embedding vector
        """
        return self._generate_bedrock_embedding(text)

    def _generate_bedrock_embedding(self, text: str) -> List[float]:
        """Generate embedding using AWS Bedrock."""
        try:
            # Prepare request body based on model version
            if "titan-embed-text-v2" in self.model_id:
                # Titan V2 supports dimensions parameter
                body = {
                    "inputText": text,
                    "dimensions": self.dimension,
                    "normalize": True  # Unit vector normalization for better similarity
                }
            else:
                # Titan V1 or other models
                body = {"inputText": text}

            # Use bearer token, API key, or boto3
            if self.use_bearer_token:
                # Direct HTTP request with Bearer token
                # Try Bearer token first, then fall back to x-api-key header if needed
                url = f"{self.bedrock_endpoint}/model/{self.model_id}/invoke"

                # First try: Bearer token in Authorization header
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.bearer_token}"
                }

                response = requests.post(
                    url,
                    json=body,
                    headers=headers,
                    timeout=30
                )

                # If Bearer token fails with 403, try different authentication methods
                if response.status_code == 403:
                    logger.warning(
                        "Bearer token authentication failed (403), trying as API key header")
                    headers = {
                        "Content-Type": "application/json",
                        "x-api-key": self.bearer_token
                    }
                    response = requests.post(
                        url,
                        json=body,
                        headers=headers,
                        timeout=30
                    )

                    # Fall back to AWS credentials (boto3) if available
                    if response.status_code == 403 and hasattr(self, 'bedrock_runtime') and self.bedrock_runtime:
                        logger.warning(
                            "Bearer token methods failed, falling back to AWS credentials (boto3)")
                        try:
                            body_json = json.dumps(body)
                            response_boto = self.bedrock_runtime.invoke_model(
                                modelId=self.model_id,
                                body=body_json,
                                contentType="application/json",
                                accept="application/json"
                            )
                            response_body = json.loads(
                                response_boto["body"].read())
                            embedding = response_body.get("embedding", [])
                            if not embedding:
                                raise Exception(
                                    "Empty embedding returned from Bedrock")
                            logger.info(
                                "✓ Successfully generated embedding using AWS credentials fallback")
                            # Verify dimension matches expected
                            if len(embedding) != self.dimension:
                                logger.warning(
                                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(embedding)}"
                                )
                            return embedding
                        except Exception as boto_error:
                            logger.error(
                                f"AWS credentials fallback also failed: {str(boto_error)}")
                            # Continue to raise the original error below

                response.raise_for_status()
                response_data = response.json()
                embedding = response_data.get("embedding", [])
            elif self.use_api_key:
                # Direct HTTP request with API key
                url = f"{self.bedrock_endpoint}/model/{self.model_id}/invoke"
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key
                }

                response = requests.post(
                    url,
                    json=body,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                response_data = response.json()
                embedding = response_data.get("embedding", [])
            else:
                # Use boto3 (existing code)
                body_json = json.dumps(body)
                response = self.bedrock_runtime.invoke_model(
                    modelId=self.model_id,
                    body=body_json,
                    contentType="application/json",
                    accept="application/json"
                )
                response_body = json.loads(response["body"].read())
                embedding = response_body.get("embedding", [])

            if not embedding:
                raise Exception("Empty embedding returned from Bedrock")

            # Verify dimension matches expected
            if len(embedding) != self.dimension:
                logger.warning(
                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(embedding)}"
                )

            return embedding

        except requests.exceptions.RequestException as e:
            error_details = str(e)
            logger.error(f"Bedrock API request error: {error_details}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    # Try different error response formats
                    error_message = (
                        error_data.get("Message") or
                        error_data.get("message") or
                        error_data.get("error", {}).get("message") or
                        error_data.get("error", {}).get("Message") or
                        ""
                    )
                    error_code = (
                        error_data.get("code") or
                        error_data.get("error", {}).get("code") or
                        f"HTTP {e.response.status_code}"
                    )
                    logger.error(f"Bedrock API error code: {error_code}")
                    logger.error(f"Bedrock API error message: {error_message}")
                    error_details = f"{error_code}: {error_message}" if error_message else error_code
                except Exception as parse_error:
                    error_text = e.response.text if hasattr(
                        e.response, 'text') else str(e.response)
                    logger.error(
                        f"Bedrock API error response (raw): {error_text}")
                    logger.error(
                        f"Failed to parse error response: {parse_error}")
                    error_details = f"{error_details} - Response: {error_text[:500]}"
            raise Exception(f"Failed to generate embedding: {error_details}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(
                f"AWS Bedrock embedding error: {error_code} - {str(e)}")
            raise Exception(f"Failed to generate embedding: {error_code}")
        except Exception as e:
            logger.error(f"Error generating Bedrock embedding: {str(e)}")
            raise

    def _generate_local_embedding(self, text: str) -> List[float]:
        """Generate embedding using local sentence-transformers model."""
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating local embedding: {str(e)}")
            raise

    def _generate_openai_embedding(self, text: str) -> List[float]:
        """Generate embedding using OpenAI."""
        try:
            response = self.openai_client.embeddings.create(
                model=self.model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating OpenAI embedding: {str(e)}")
            raise

    def get_dimension(self) -> int:
        """Get the dimension of embeddings produced by this service."""
        return self.dimension
