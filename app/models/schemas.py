"""
Pydantic models for request/response schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional


class AskRequest(BaseModel):
    """Request model for /ask endpoint."""
    user: str = Field(..., description="User display name",
                      min_length=1, max_length=100)
    question: str = Field(..., description="User question",
                          min_length=1, max_length=2000)
    conversation_id: Optional[str] = Field(
        None, description="Optional conversation ID for maintaining context across messages. If not provided, each request is treated as a new conversation.")


class AskResponse(BaseModel):
    """Response model for /ask endpoint."""
    answer: str = Field(..., description="AI-generated answer")
    sources: list[str] = Field(...,
                               description="List of source files or documents")


class AddEmbeddingRequest(BaseModel):
    """Request body for /add-embedding endpoint."""
    text: str = Field(..., description="Text content to embed", min_length=1)
    metadata: Optional[str] = Field(
        None, description="Additional metadata as JSON string or plain text")


class AddEmbeddingResponse(BaseModel):
    """Response model for /add-embedding endpoint."""
    success: bool = Field(..., description="Whether the operation succeeded")
    chunks_indexed: int = Field(..., description="Number of chunks indexed")
    message: str = Field(..., description="Status message")
