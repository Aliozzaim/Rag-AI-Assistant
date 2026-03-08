"""
AWS Bedrock service for LLM integration.
Uses inference profiles with boto3 for model invocation.
"""
import logging
import json
from typing import List, Dict, Optional
import boto3
from botocore.exceptions import ClientError, BotoCoreError
from app.core.config import settings

logger = logging.getLogger(__name__)


class BedrockService:
    """Service for interacting with AWS Bedrock LLM."""

    def __init__(self):
        """Initialize Bedrock client with inference profile."""
        if not settings.bedrock_inference_profile_arn:
            raise ValueError(
                "BEDROCK_INFERENCE_PROFILE_ARN is required. Please set it in your .env file.")

        self.inference_profile_arn = settings.bedrock_inference_profile_arn
        self.region = settings.aws_region

        # Extract inference profile ID from ARN
        # ARN format: arn:aws:bedrock:region:account:inference-profile/profile-id
        self.inference_profile_id = self.inference_profile_arn.split("/")[-1]
        logger.info(
            f"Initializing BedrockService with inference profile: {self.inference_profile_id}")
        logger.info(f"Inference Profile ARN: {self.inference_profile_arn}")
        logger.info(f"Region: {self.region}")

        # Initialize boto3 client
        # Priority: AWS Profile > AWS credentials > default credential chain
        if settings.aws_profile:
            session = boto3.Session(profile_name=settings.aws_profile)
            self.bedrock_runtime = session.client(
                service_name="bedrock-runtime",
                region_name=settings.aws_region
            )
            logger.info(f"✓ Using AWS Profile: {settings.aws_profile}")
        elif settings.aws_access_key_id and settings.aws_secret_access_key:
            self.bedrock_runtime = boto3.client(
                service_name="bedrock-runtime",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key
            )
            logger.info(f"✓ Using AWS credentials")
        else:
            self.bedrock_runtime = boto3.client(
                service_name="bedrock-runtime",
                region_name=settings.aws_region
            )
            logger.info("✓ Using AWS default credential chain")

    def build_prompt(self, question: str, chunks: List[Dict], conversation_history: Optional[List[Dict]] = None) -> str:
        """
        Build a prompt for the LLM with retrieved chunks and instructions.

        Args:
            question: User's question
            chunks: Retrieved knowledge base chunks (can be empty)
            conversation_history: Optional list of previous messages in format [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

        Returns:
            Formatted prompt string
        """
        # Extract text from chunks
        chunk_texts = []
        for chunk in chunks:
            text = chunk.get("payload", {}).get("text", "")
            source = chunk.get("payload", {}).get("source", "unknown")
            if text:
                chunk_texts.append(f"Source: {source}\n{text}")

        chunks_content = "\n\n---\n\n".join(chunk_texts)

        # Build conversation history context
        conversation_context = ""
        if conversation_history and len(conversation_history) > 0:
            logger.info(
                f"Building conversation context from {len(conversation_history)} messages")
            conversation_context = "\n\nPrevious Conversation:\n"
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    conversation_context += f"User: {content}\n"
                elif role == "assistant":
                    conversation_context += f"Assistant: {content}\n"
            conversation_context += "\n"
            logger.debug(
                f"Conversation context length: {len(conversation_context)} characters")
        else:
            logger.debug(
                "No conversation history provided - building prompt without context")

        # Build prompt based on whether we have chunks or not
        if chunks_content:
            # We have relevant chunks - use them
            prompt = f"""You are  a helpful AI assistant for Softwere engineers. Your role is to answer questions based on the provided knowledge base chunks below.{conversation_context}

INSTRUCTIONS:
1. Answer the question using ONLY the information provided in the chunks below when available
2. Include the source file/document names in your answer when referencing information
3. Be concise and helpful
4. If multiple sources are relevant, mention all of them
5. If the question is conversational (like "how are you?"), respond naturally and conversationally
6. Use conversation history context to understand follow-up questions and references to previous messages
7. IMPORTANT: If the chunks do not contain enough information to answer the question, or if you're not certain about the answer, you MUST say so clearly. For example:
   - "I couldn't find specific information about [topic] in the knowledge base. Could you provide more details or clarify what you're looking for?"
   - "The available information doesn't fully answer your question. Based on what I found: [partial answer]. Could you clarify [specific aspect]?"
   - "I'm not certain about this based on the available documentation. Could you rephrase your question or provide more context?"
8. Do NOT make up information or provide generic answers if the knowledge base doesn't contain relevant information
9. If you cannot answer confidently, ask for clarification rather than guessing

Knowledge Base Chunks:
{chunks_content}

Current Question: {question}

Answer:"""
        else:
            # No chunks found - ask for clarification
            prompt = f"""You are Sparky, a helpful AI assistant for Microsoft Teams. 

IMPORTANT: No relevant information was found in the knowledge base for this question.{conversation_context}

INSTRUCTIONS:
1. Politely inform the user that you couldn't find relevant information in the knowledge base
2. Ask for clarification or more specific details about what they're looking for
3. Be helpful and suggest ways they could rephrase their question
4. Use conversation history to understand context and follow-up questions
5. Do NOT provide generic answers or make up information
6. If the question is conversational (like "how are you?"), respond naturally

Current Question: {question}

Answer:"""

        return prompt

    def generate_answer(self, prompt: str, max_tokens: int = 1000) -> str:
        """
        Generate answer using AWS Bedrock LLM with inference profile.

        Args:
            prompt: The prompt to send to the LLM
            max_tokens: Maximum tokens in the response

        Returns:
            Generated answer string

        Raises:
            Exception: If LLM call fails
        """
        logger.info(
            f"Generating answer with inference profile: {self.inference_profile_id}")
        logger.info(f"Prompt length: {len(prompt)} characters")
        logger.info(f"Max tokens: {max_tokens}")

        try:
            # Determine API format based on inference profile ID
            if "nova" in self.inference_profile_id.lower():
                # Amazon Nova uses messages API
                body = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": prompt
                                }
                            ]
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": max_tokens,
                        "temperature": 0.7,
                        "topP": 0.9
                    }
                }
            elif "claude" in self.inference_profile_id.lower():
                # Claude uses messages API
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.7,
                    "top_p": 0.9
                }
            elif "llama" in self.inference_profile_id.lower():
                # Meta Llama uses prompt-based API
                body = {
                    "prompt": prompt,
                    "max_gen_len": max_tokens,
                    "temperature": 0.7,
                    "top_p": 0.9
                }
            elif "mistral" in self.inference_profile_id.lower():
                # Mistral uses messages API
                body = {
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                    "top_p": 0.9
                }
            else:
                # Default: Claude v2 text completion API
                body = {
                    "prompt": prompt,
                    "max_tokens_to_sample": max_tokens,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "stop_sequences": ["\n\nHuman:"]
                }

            # Use boto3 to invoke model with inference profile ID
            body_json = json.dumps(body)
            response = self.bedrock_runtime.invoke_model(
                modelId=self.inference_profile_id,
                body=body_json,
                contentType="application/json",
                accept="application/json"
            )
            response_body = json.loads(response["body"].read())
            logger.info(
                "✓ Successfully invoked Bedrock with inference profile")

            # Parse response based on model type
            if "nova" in self.inference_profile_id.lower():
                # Amazon Nova response format
                answer = response_body.get("output", {}).get("message", {}).get(
                    "content", [{}])[0].get("text", "").strip()
                if not answer:
                    answer = response_body.get("message", {}).get(
                        "content", [{}])[0].get("text", "").strip()
            elif "llama" in self.inference_profile_id.lower():
                # Meta Llama response format
                answer = response_body.get("generation", "").strip()
            elif "mistral" in self.inference_profile_id.lower():
                # Mistral response format
                answer = response_body.get("outputs", [{}])[0].get(
                    "text", "").strip() if isinstance(response_body.get("outputs"), list) else ""
                if not answer:
                    answer = response_body.get("text", "").strip()
            elif "claude" in self.inference_profile_id.lower():
                # Claude response format
                answer = response_body.get("content", [{}])[
                    0].get("text", "").strip()
            else:
                # Default: Claude v2 response format
                answer = response_body.get("completion", "").strip()

            logger.info(f"Generated answer with {len(answer)} characters")
            return answer

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(f"AWS Bedrock client error: {error_code} - {str(e)}")
            raise Exception(f"Failed to generate answer: {error_code}")
        except BotoCoreError as e:
            logger.error(f"AWS Bedrock error: {str(e)}")
            raise Exception(f"Failed to connect to AWS Bedrock: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error generating answer: {str(e)}")
            raise

    def health_check(self) -> bool:
        """
        Check if Bedrock service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        logger.info("Checking Bedrock service health")
        try:
            # Try a simple invoke_model call to verify connectivity
            # Use a minimal test prompt
            test_body = {
                "prompt": "test",
                "max_tokens_to_sample": 1
            }
            self.bedrock_runtime.invoke_model(
                modelId=self.inference_profile_id,
                body=json.dumps(test_body),
                contentType="application/json",
                accept="application/json"
            )
            logger.info("✓ Bedrock service health check passed")
            return True
        except Exception as e:
            logger.error(f"✗ Bedrock service health check failed: {str(e)}")
            return False
